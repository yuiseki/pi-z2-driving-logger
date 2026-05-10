"""Traccar spool queue: pending → sending → sent / failed."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class TraccarQueue:
    """File-based spool queue for Traccar payloads.

    Directory structure::

        queue_dir/
            pending/    ← new payloads waiting to be sent
            sending/    ← in-flight (moved back to pending on startup)
            sent/       ← successfully delivered
            failed/     ← corrupt or permanently rejected (HTTP 4xx)
    """

    SUBDIRS = ("pending", "sending", "sent", "failed")

    def __init__(self, queue_dir: str) -> None:
        self._queue_dir = queue_dir
        self._dirs = {s: os.path.join(queue_dir, s) for s in self.SUBDIRS}
        for d in self._dirs.values():
            os.makedirs(d, exist_ok=True)

    # -----------------------------------------------------------------------
    # Public: enqueue
    # -----------------------------------------------------------------------

    def enqueue(self, payload: dict) -> str:
        """Persist payload JSON in pending/. Returns the filename (empty on error)."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        micro = str(int(time.time() * 1_000_000) % 1_000_000).zfill(6)
        kind = payload.get("kind", "unknown")
        event_type = payload.get("event_type", "")
        suffix = f"event-{event_type}" if event_type else kind
        filename = f"{ts}-{micro}-{suffix}.json"
        path = os.path.join(self._dirs["pending"], filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except OSError as exc:
            logger.error("Traccar enqueue failed: %s", exc)
            return ""
        logger.debug("Traccar queued: %s", filename)
        return filename

    # -----------------------------------------------------------------------
    # Public: list
    # -----------------------------------------------------------------------

    def list_pending(self) -> list:
        """Return sorted list of filenames in pending/."""
        try:
            return sorted(os.listdir(self._dirs["pending"]))
        except OSError:
            return []

    # -----------------------------------------------------------------------
    # Public: recovery
    # -----------------------------------------------------------------------

    def recover_sending(self) -> int:
        """Move leftover sending/ files back to pending/ (call once at startup)."""
        recovered = 0
        try:
            for fname in os.listdir(self._dirs["sending"]):
                src = os.path.join(self._dirs["sending"], fname)
                dst = os.path.join(self._dirs["pending"], fname)
                try:
                    os.rename(src, dst)
                    recovered += 1
                except OSError as exc:
                    logger.error("Recovery rename failed %s: %s", fname, exc)
        except OSError:
            pass
        if recovered:
            logger.info("Traccar queue: recovered %d sending→pending", recovered)
        return recovered

    # -----------------------------------------------------------------------
    # Public: flush
    # -----------------------------------------------------------------------

    def flush(
        self,
        endpoint: str,
        device_id: str,
        max_count: int = 50,
        timeout_s: float = 5.0,
        payload_to_url_fn: Optional[Callable] = None,
    ) -> tuple:
        """Send up to max_count pending payloads.

        Returns (sent, requeued, failed) counts.
        """
        if payload_to_url_fn is None:
            from .traccar import payload_to_url
            payload_to_url_fn = payload_to_url

        pending = self.list_pending()[:max_count]
        sent_count = requeued_count = failed_count = 0

        for fname in pending:
            src = os.path.join(self._dirs["pending"], fname)
            sending_path = os.path.join(self._dirs["sending"], fname)

            # Move pending → sending
            try:
                os.rename(src, sending_path)
            except OSError as exc:
                logger.warning("Cannot move to sending %s: %s", fname, exc)
                continue

            # Load and validate JSON
            try:
                with open(sending_path, encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Corrupt payload %s: %s — failed", fname, exc)
                self._move(sending_path, self._dirs["failed"], fname)
                failed_count += 1
                continue

            # Send
            try:
                url = payload_to_url_fn(endpoint, device_id, payload)
                req = Request(url)
                with urlopen(req, timeout=timeout_s) as resp:
                    status = resp.status

                if 200 <= status < 300:
                    self._move(sending_path, self._dirs["sent"], fname)
                    sent_count += 1
                    logger.debug("Traccar sent: %s", fname)
                elif 400 <= status < 500:
                    logger.error("Traccar HTTP %d for %s — failed", status, fname)
                    self._move(sending_path, self._dirs["failed"], fname)
                    failed_count += 1
                else:
                    logger.warning("Traccar HTTP %d for %s — requeue", status, fname)
                    self._move(sending_path, self._dirs["pending"], fname)
                    requeued_count += 1

            except HTTPError as exc:
                if 400 <= exc.code < 500:
                    logger.error("Traccar HTTP %d for %s — failed", exc.code, fname)
                    self._move(sending_path, self._dirs["failed"], fname)
                    failed_count += 1
                else:
                    logger.warning("Traccar HTTP %s for %s — requeue", exc, fname)
                    self._move(sending_path, self._dirs["pending"], fname)
                    requeued_count += 1
            except (URLError, OSError, TimeoutError) as exc:
                logger.warning("Traccar send failed %s: %s — requeue", fname, exc)
                self._move(sending_path, self._dirs["pending"], fname)
                requeued_count += 1

        if sent_count + requeued_count + failed_count > 0:
            logger.info(
                "Traccar flush: sent=%d requeued=%d failed=%d",
                sent_count, requeued_count, failed_count,
            )
        return sent_count, requeued_count, failed_count

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _move(self, src: str, dst_dir: str, fname: str) -> None:
        dst = os.path.join(dst_dir, fname)
        try:
            os.rename(src, dst)
        except OSError as exc:
            logger.error("Cannot move %s → %s: %s", src, dst_dir, exc)


# ---------------------------------------------------------------------------
# Background uploader thread
# ---------------------------------------------------------------------------

class TraccarUploader:
    """Background thread that flushes the TraccarQueue at a fixed interval."""

    def __init__(
        self,
        queue: TraccarQueue,
        endpoint: str,
        device_id: str,
        flush_interval_s: float = 10.0,
        timeout_s: float = 5.0,
        max_retry_per_flush: int = 50,
    ) -> None:
        self._queue = queue
        self._endpoint = endpoint
        self._device_id = device_id
        self._flush_interval_s = flush_interval_s
        self._timeout_s = timeout_s
        self._max_retry_per_flush = max_retry_per_flush
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._queue.recover_sending()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="traccar-uploader"
        )
        self._thread.start()
        logger.info(
            "Traccar uploader started: endpoint=%s device_id=%s interval=%.0fs",
            self._endpoint,
            self._device_id,
            self._flush_interval_s,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Traccar uploader stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._queue.flush(
                    endpoint=self._endpoint,
                    device_id=self._device_id,
                    max_count=self._max_retry_per_flush,
                    timeout_s=self._timeout_s,
                )
            except Exception as exc:
                logger.error("Traccar flush error: %s", exc)
            self._stop_event.wait(self._flush_interval_s)
