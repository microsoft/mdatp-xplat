from __future__ import annotations

import threading
from pathlib import Path

import mde


SAMPLE_STREAM = """Total Events: 0 Total Processed Events: 0 Urgent Events: 0 Time: 0s. Throughput: 0 events/sec. (Press Control-C to stop)
=========== Top 0 Hot Event Sources ===========
count  signing id                               team id               path
=========== Top 0 Hot Event Targets ===========
count  target path
Total Events: 604 Total Processed Events: 165 Urgent Events: 4 Time: 1s. Throughput: 972 events/sec. (Press Control-C to stop)
=========== Top 3 Hot Event Sources ===========
count  signing id                               team id               path
192    com.microsoft.VSCode.helper              UBF8T346G9            \x1b[32m/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/Code Helper (Plugin)\x1b[0m
184    com.apple.bash                                                 \x1b[32m/bin/bash\x1b[0m
13     com.apple.dt.xcode_select.tool-shim                            \x1b[32m/usr/bin/git\x1b[0m
=========== Top 0 Hot Event Targets ===========
count  target path
"""


class _FakePopen:
    def __init__(self, stdout_text: str, return_code: int = 0):
        self._stdout = stdout_text
        self._stderr = ""
        self.returncode = None
        self._rc = return_code
        self._signal_sent = False

    def poll(self):
        return self.returncode

    def send_signal(self, _sig):
        self._signal_sent = True
        self.returncode = self._rc

    def communicate(self, timeout=None):
        self.returncode = self._rc
        return self._stdout, self._stderr

    def terminate(self):
        self.returncode = self._rc

    def kill(self):
        self.returncode = self._rc


def test_parse_hot_event_sources_output_and_top_sources():
    snapshots = mde.parse_hot_event_sources_output(SAMPLE_STREAM)

    assert len(snapshots) == 2
    assert snapshots[-1]["total_events"] == 604
    assert len(snapshots[-1]["sources"]) == 3
    assert snapshots[-1]["sources"][0]["path"].startswith("/Applications/Visual Studio Code.app")

    top = mde.top_hot_event_sources(snapshots, top_n=2)
    assert len(top) == 2
    assert top[0]["count"] == 192
    assert top[0]["signing_id"] == "com.microsoft.VSCode.helper"
    assert top[1]["count"] == 184


def test_hot_event_capture_writes_structured_json(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mde.subprocess, "Popen", lambda *a, **k: _FakePopen(SAMPLE_STREAM))

    out = tmp_path / "hot_events.json"
    samples = mde.capture_hot_event_sources(
        duration_seconds=0.01,
        output_path=out,
        interval_seconds=0.01,
    )

    assert samples == 2
    assert out.exists()
    data = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert data["snapshot_count"] == 2
    assert data["top_hot_event_sources"][0]["count"] == 192
    assert data["top_hot_event_sources"][0]["path"].startswith("/Applications/Visual Studio Code.app")


def test_hot_event_capture_stops_immediately_when_event_set(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mde.subprocess, "Popen", lambda *a, **k: _FakePopen(SAMPLE_STREAM))

    stop = threading.Event()
    stop.set()

    out = tmp_path / "stopped.json"
    samples = mde.capture_hot_event_sources(
        duration_seconds=0.01,
        output_path=out,
        interval_seconds=0.01,
        stop_event=stop,
    )

    assert samples >= 0
    assert out.exists()
    data = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert "snapshot_count" in data
    assert "top_hot_event_sources" in data


def test_hot_event_capture_zero_duration_is_noop(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mde.subprocess, "Popen", lambda *a, **k: _FakePopen(SAMPLE_STREAM))

    out = tmp_path / "noop.jsonl"
    samples = mde.capture_hot_event_sources(
        duration_seconds=0,
        output_path=out,
        interval_seconds=0.1,
    )

    assert samples == 0
    assert not out.exists()
