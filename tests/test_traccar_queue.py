"""Tests for Traccar spool queue (traccar_queue.py)."""

import json
import os
import tempfile
import time

import pytest

from pi_z2_driving_logger.traccar_queue import TraccarQueue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_queue(tmp_path) -> TraccarQueue:
    return TraccarQueue(str(tmp_path / "traccar-queue"))


def _sample_position_payload() -> dict:
    return {
        "kind": "position",
        "lat": 35.681236,
        "lon": 139.767125,
        "timestamp": 1778371200,
        "speed": 9.26,
        "bearing": 270.0,
        "altitude": 0.0,
        "accuracy": 9.8,
        "hdop": 1.96,
        "driver_state": "self",
        "source": "pi_z2_driving_logger",
        "session_id": "20260510-093000",
        "fix_quality": 1,
        "satellites_used": 7,
    }


def _sample_event_payload(event_type: str = "walk_poi") -> dict:
    return {
        "kind": "event",
        "event_type": event_type,
        "lat": 35.681236,
        "lon": 139.767125,
        "timestamp": 1778371200,
        "speed": 0.0,
        "bearing": 0.0,
        "altitude": 0.0,
        "accuracy": 9.8,
        "hdop": 1.96,
        "driver_state": "other",
        "source": "maker_phat_left_button",
        "session_id": "20260510-093000",
        "fix_quality": 1,
        "satellites_used": 7,
    }


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def test_enqueue_creates_file_in_pending(tmp_path):
    q = _make_queue(tmp_path)
    fname = q.enqueue(_sample_position_payload())
    assert fname != ""
    pending_dir = os.path.join(str(tmp_path / "traccar-queue"), "pending")
    assert os.path.exists(os.path.join(pending_dir, fname))


def test_enqueue_position_filename_contains_position(tmp_path):
    q = _make_queue(tmp_path)
    fname = q.enqueue(_sample_position_payload())
    assert "position" in fname


def test_enqueue_event_filename_contains_event_type(tmp_path):
    q = _make_queue(tmp_path)
    fname = q.enqueue(_sample_event_payload("walk_poi_important"))
    assert "walk_poi_important" in fname


def test_enqueue_payload_is_valid_json(tmp_path):
    q = _make_queue(tmp_path)
    fname = q.enqueue(_sample_position_payload())
    pending_dir = os.path.join(str(tmp_path / "traccar-queue"), "pending")
    with open(os.path.join(pending_dir, fname), encoding="utf-8") as f:
        data = json.load(f)
    assert data["kind"] == "position"


# ---------------------------------------------------------------------------
# List pending
# ---------------------------------------------------------------------------

def test_list_pending_empty(tmp_path):
    q = _make_queue(tmp_path)
    assert q.list_pending() == []


def test_list_pending_returns_enqueued(tmp_path):
    q = _make_queue(tmp_path)
    q.enqueue(_sample_position_payload())
    q.enqueue(_sample_event_payload())
    pending = q.list_pending()
    assert len(pending) == 2


def test_list_pending_is_sorted(tmp_path):
    q = _make_queue(tmp_path)
    for _ in range(3):
        q.enqueue(_sample_position_payload())
        time.sleep(0.01)
    pending = q.list_pending()
    assert pending == sorted(pending)


# ---------------------------------------------------------------------------
# Recover sending
# ---------------------------------------------------------------------------

def test_recover_sending_moves_files_to_pending(tmp_path):
    q = _make_queue(tmp_path)
    queue_dir = str(tmp_path / "traccar-queue")
    sending_dir = os.path.join(queue_dir, "sending")
    pending_dir = os.path.join(queue_dir, "pending")

    # Manually place a file in sending/
    fname = "20260510-093000-000001-position.json"
    with open(os.path.join(sending_dir, fname), "w") as f:
        json.dump(_sample_position_payload(), f)

    recovered = q.recover_sending()
    assert recovered == 1
    assert os.path.exists(os.path.join(pending_dir, fname))
    assert not os.path.exists(os.path.join(sending_dir, fname))


def test_recover_sending_empty_returns_zero(tmp_path):
    q = _make_queue(tmp_path)
    assert q.recover_sending() == 0


# ---------------------------------------------------------------------------
# Flush: success path (mocked HTTP)
# ---------------------------------------------------------------------------

def _make_mock_url_fn(status_code: int):
    """Return a fake payload_to_url_fn that makes flush() use a mock sender."""
    def url_fn(endpoint, device_id, payload):
        return f"http://mock/{status_code}"
    return url_fn


class _MockResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _flush_with_mock(q, status_code, max_count=50, monkeypatch=None):
    """Run flush() with urllib.request.urlopen mocked to return given status."""
    import pi_z2_driving_logger.traccar_queue as tq_module

    original_urlopen = tq_module.urlopen

    def fake_urlopen(req, timeout=5.0):
        return _MockResponse(status_code)

    tq_module.urlopen = fake_urlopen
    try:
        result = q.flush(
            endpoint="http://mock/",
            device_id="pi-z2-wh",
            max_count=max_count,
            timeout_s=5.0,
            payload_to_url_fn=lambda ep, did, p: f"http://mock/?id={did}",
        )
    finally:
        tq_module.urlopen = original_urlopen
    return result


def test_flush_success_moves_to_sent(tmp_path):
    q = _make_queue(tmp_path)
    q.enqueue(_sample_position_payload())

    sent, requeued, failed = _flush_with_mock(q, 200)
    assert sent == 1
    assert requeued == 0
    assert failed == 0

    queue_dir = str(tmp_path / "traccar-queue")
    assert len(os.listdir(os.path.join(queue_dir, "sent"))) == 1
    assert len(os.listdir(os.path.join(queue_dir, "pending"))) == 0


def test_flush_http_400_moves_to_failed(tmp_path):
    import pi_z2_driving_logger.traccar_queue as tq_module
    from urllib.error import HTTPError

    q = _make_queue(tmp_path)
    q.enqueue(_sample_position_payload())

    original_urlopen = tq_module.urlopen

    def fake_urlopen(req, timeout=5.0):
        raise HTTPError(req, 400, "Bad Request", {}, None)

    tq_module.urlopen = fake_urlopen
    try:
        sent, requeued, failed = q.flush(
            endpoint="http://mock/",
            device_id="pi-z2-wh",
            payload_to_url_fn=lambda ep, did, p: "http://mock/",
        )
    finally:
        tq_module.urlopen = original_urlopen

    assert failed == 1
    queue_dir = str(tmp_path / "traccar-queue")
    assert len(os.listdir(os.path.join(queue_dir, "failed"))) == 1
    assert len(os.listdir(os.path.join(queue_dir, "pending"))) == 0


def test_flush_network_error_requeues_to_pending(tmp_path):
    import pi_z2_driving_logger.traccar_queue as tq_module
    from urllib.error import URLError

    q = _make_queue(tmp_path)
    q.enqueue(_sample_position_payload())

    original_urlopen = tq_module.urlopen

    def fake_urlopen(req, timeout=5.0):
        raise URLError("connection refused")

    tq_module.urlopen = fake_urlopen
    try:
        sent, requeued, failed = q.flush(
            endpoint="http://mock/",
            device_id="pi-z2-wh",
            payload_to_url_fn=lambda ep, did, p: "http://mock/",
        )
    finally:
        tq_module.urlopen = original_urlopen

    assert requeued == 1
    queue_dir = str(tmp_path / "traccar-queue")
    assert len(os.listdir(os.path.join(queue_dir, "pending"))) == 1


def test_flush_corrupt_json_moves_to_failed(tmp_path):
    q = _make_queue(tmp_path)
    queue_dir = str(tmp_path / "traccar-queue")
    # Write corrupt JSON directly to pending/
    fname = "20260510-093000-corrupt.json"
    with open(os.path.join(queue_dir, "pending", fname), "w") as f:
        f.write("not valid json {{{")

    sent, requeued, failed = _flush_with_mock(q, 200)
    assert failed == 1
    assert len(os.listdir(os.path.join(queue_dir, "failed"))) == 1


def test_flush_max_count_limits_items(tmp_path):
    q = _make_queue(tmp_path)
    for _ in range(10):
        q.enqueue(_sample_position_payload())
        time.sleep(0.005)

    sent, requeued, failed = _flush_with_mock(q, 200, max_count=3)
    assert sent == 3
    queue_dir = str(tmp_path / "traccar-queue")
    # 7 remaining in pending
    assert len(os.listdir(os.path.join(queue_dir, "pending"))) == 7


def test_flush_http_500_requeues(tmp_path):
    import pi_z2_driving_logger.traccar_queue as tq_module
    from urllib.error import HTTPError

    q = _make_queue(tmp_path)
    q.enqueue(_sample_position_payload())

    original_urlopen = tq_module.urlopen
    def fake_urlopen(req, timeout=5.0):
        raise HTTPError(req, 500, "Internal Server Error", {}, None)
    tq_module.urlopen = fake_urlopen
    try:
        sent, requeued, failed = q.flush(
            endpoint="http://mock/",
            device_id="pi-z2-wh",
            payload_to_url_fn=lambda ep, did, p: "http://mock/",
        )
    finally:
        tq_module.urlopen = original_urlopen

    assert requeued == 1
    queue_dir = str(tmp_path / "traccar-queue")
    assert len(os.listdir(os.path.join(queue_dir, "pending"))) == 1
