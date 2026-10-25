"""Thin, proven helpers for driving MDE from pytest.

No classes, no framework — just the handful of `mdatp` calls and the
EICAR threat-count detection that the demos rely on. Each helper shells
out to the same commands the manual experiment used.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Standard EICAR antivirus test string (harmless — used to verify AV scanning).
EICAR_STRING = (
    "X5O!P%@AP[4\\PZX54(P^)7CC)7}"
    "$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


def _run(args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    # mdatp queries can be slow (e.g. `exclusion list` takes ~20s, and far
    # longer while the daemon is saturated scanning a fresh node_modules), so
    # the default timeout is generous to avoid spurious TimeoutExpired errors.
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


# ── MDE state ────────────────────────────────────────────────────────────

def rtp_enabled() -> bool:
    """True if real-time protection is on."""
    result = _run(["mdatp", "health", "--field", "real_time_protection_enabled"])
    return result.returncode == 0 and "true" in (result.stdout or "").lower()


def threat_count() -> int:
    """Number of entries in the MDE threat list.

    Counts lines starting with "Id:" — the monotonic signal the EICAR
    experiment uses. Each detection adds exactly one entry.
    """
    result = _run(["mdatp", "threat", "list"])
    if result.returncode != 0:
        return 0
    return sum(
        1 for line in (result.stdout or "").splitlines()
        if line.strip().startswith("Id:")
    )


# ── Performance profiles ─────────────────────────────────────────────────

def list_applied_profiles() -> List[str]:
    result = _run(["sudo", "mdatp", "performance-profiles", "list-applied"])
    applied = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        lower = line.lower()
        if not line or lower.startswith("merge policy:"):
            continue
        if lower.startswith("no applied performance profiles"):
            continue
        if line in ("---", "====================================="):
            continue
        applied.append(line.split()[0])
    return applied


def apply_profiles(names: List[str]) -> None:
    for name in names:
        _run(["sudo", "mdatp", "performance-profiles", "apply", "--name", name])


def remove_profiles(names: List[str]) -> None:
    for name in names:
        _run(["sudo", "mdatp", "performance-profiles", "remove", "--name", name])


# ── AV exclusions ────────────────────────────────────────────────────────

def add_exclusion(path: Path) -> None:
    _run(["sudo", "mdatp", "exclusion", "folder", "add", "--path", str(path)])


def remove_exclusion(path: Path) -> None:
    _run(["sudo", "mdatp", "exclusion", "folder", "remove", "--path", str(path)])


def list_exclusions() -> str:
    return _run(["mdatp", "exclusion", "list"]).stdout or ""


def list_exclusion_paths() -> List[str]:
    """Return the folder-exclusion paths currently configured in MDE."""
    import json

    result = _run(["mdatp", "exclusion", "list", "--output", "json"])
    if result.returncode != 0 or not (result.stdout or "").strip():
        return []
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return []
    entries = data if isinstance(data, list) else data.get("exclusions", data.get("value", []))
    paths = []
    for e in entries:
        if isinstance(e, dict):
            value = e.get("value", e.get("path", ""))
            if value:
                paths.append(value.rstrip("/"))
    return paths


# ── MDE scanning load (the in-window signal that exclusions/profiles work) ─
#
# NOTE: `mdatp diagnostic real-time-protection-statistics` was tried as a
# "files scanned" metric but is unusable here: its `totalFilesScanned` is a
# PER-PROCESS LIFETIME total across every process on the system (Microsoft Edge,
# Spotlight's mds_stores, launchd, ...). The build is a rounding error in that
# sum, and the counter list resets/repopulates around profile changes, so the
# before/after delta swings wildly (seen: -32058 one run, +5.6M the next). The
# clean signal is the MDE daemon's CPU sampled DURING the build window, below:
# background app scanning is ~constant across phases, so the drop is the build's.

class _CpuMonitor:
    """Background sampler of the MDE scanning daemon's %CPU; reports the average."""

    PROCESS = "wdavdaemon_unprivileged"

    def __init__(self, interval: float = 2.0):
        self._interval = interval
        self._stop = threading.Event()
        self._samples: List[float] = []
        self._thread: Optional[threading.Thread] = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            result = subprocess.run(
                ["ps", "-eo", "pid,%cpu,comm"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            for line in (result.stdout or "").splitlines():
                if self.PROCESS in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            self._samples.append(float(parts[1]))
                        except ValueError:
                            pass
                    break
            self._stop.wait(self._interval)

    def __enter__(self) -> "_CpuMonitor":
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def average(self) -> Optional[float]:
        if not self._samples:
            return None
        return sum(self._samples) / len(self._samples)


def capture_hot_event_sources(
    duration_seconds: float,
    output_path: Path,
    *,
    interval_seconds: float = 2.0,
    stop_event: Optional[threading.Event] = None,
) -> int:
    """Capture hot-event-sources telemetry for a fixed window and write JSON.

    The mdatp command streams until interrupted, so this helper runs it once,
    waits for ``duration_seconds`` (or ``stop_event``), interrupts it, parses
    the text stream into structured snapshots, and writes a JSON report.

    Returns the number of parsed snapshots.
    """
    if duration_seconds <= 0:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    start_wall = time.time()
    start_mono = time.perf_counter()
    cmd = ["sudo", "mdatp", "diagnostic", "hot-event-sources", "--output", "json"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    deadline = start_mono + duration_seconds
    while time.perf_counter() < deadline:
        if stop_event is not None and stop_event.is_set():
            break
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        sleep_for = min(max(interval_seconds, 0.05), remaining)
        if stop_event is not None and stop_event.wait(timeout=sleep_for):
            break
        if stop_event is None:
            time.sleep(sleep_for)

    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)

    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

    elapsed = time.perf_counter() - start_mono
    snapshots = parse_hot_event_sources_output(stdout or "")
    report = {
        "command": cmd,
        "start_ts": start_wall,
        "elapsed_seconds": elapsed,
        "return_code": proc.returncode,
        "snapshot_count": len(snapshots),
        "top_hot_event_sources": top_hot_event_sources(snapshots, top_n=10),
        "snapshots": snapshots,
        "stderr": stderr or "",
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return len(snapshots)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SUMMARY_RE = re.compile(
    r"Total Events:\s*(?P<total>\d+)\s+"
    r"Total Processed Events:\s*(?P<processed>\d+)\s+"
    r"Urgent Events:\s*(?P<urgent>\d+)\s+"
    r"Time:\s*(?P<time>[0-9.]+)s",
    re.IGNORECASE,
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def parse_hot_event_sources_output(raw_output: str) -> List[Dict[str, Any]]:
    """Parse mdatp hot-event-sources stream text into structured snapshots."""
    if not raw_output:
        return []

    cleaned = _strip_ansi(raw_output)
    lines = [line.rstrip("\n") for line in cleaned.splitlines()]
    snapshots: List[Dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        match = _SUMMARY_RE.search(line)
        if not match:
            i += 1
            continue

        snapshot: Dict[str, Any] = {
            "total_events": int(match.group("total")),
            "processed_events": int(match.group("processed")),
            "urgent_events": int(match.group("urgent")),
            "time_seconds": float(match.group("time")),
            "sources": [],
        }

        i += 1
        while i < len(lines) and "Hot Event Sources" not in lines[i]:
            i += 1

        if i < len(lines):
            i += 1  # consume the "Top ... Hot Event Sources" separator line
            if i < len(lines) and lines[i].strip().lower().startswith("count"):
                i += 1

            while i < len(lines):
                row = lines[i].strip()
                if not row:
                    i += 1
                    continue
                if row.startswith("===========") or row.startswith("Total Events:"):
                    break

                parts = re.split(r"\s{2,}", row)
                if len(parts) >= 3:
                    try:
                        count = int(parts[0])
                    except ValueError:
                        i += 1
                        continue

                    if len(parts) == 3:
                        signing_id = parts[1]
                        team_id = ""
                        path = parts[2]
                    else:
                        signing_id = parts[1]
                        team_id = parts[2]
                        path = parts[3]

                    snapshot["sources"].append(
                        {
                            "count": count,
                            "signing_id": signing_id,
                            "team_id": team_id,
                            "path": path,
                        }
                    )
                i += 1

        snapshots.append(snapshot)
        i += 1

    return snapshots


def top_hot_event_sources(snapshots: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """Return top-N hot event sources from the latest parsed snapshot."""
    if top_n <= 0 or not snapshots:
        return []
    latest_sources = snapshots[-1].get("sources", [])
    sorted_sources = sorted(latest_sources, key=lambda row: row.get("count", 0), reverse=True)
    return sorted_sources[:top_n]


# ── EICAR detection (the proven signal) ──────────────────────────────────

def eicar_detected(target_dir: Path, timeout: int = 30, poll: float = 1.0) -> bool:
    """Drop an EICAR file in target_dir and report whether RTP catches it.

    Captures the threat count first, writes EICAR to a timestamped file,
    then polls until the threat count rises (detection) or the file is
    removed (quarantine). Returns False if neither happens within timeout.
    """
    result = eicar_probe(target_dir, timeout=timeout, poll=poll)
    try:
        if result.path.exists():
            result.path.unlink()
    except OSError:
        pass
    return result.detected


@dataclass
class EicarResult:
    detected: bool
    path: Path
    count_before: int
    count_after: int
    file_exists: bool
    elapsed: float


def _write_eicar(path: Path) -> None:
    """Drop the EICAR string via a child-process redirect.

    Real-time protection reliably scans a file written by a separate process,
    but in some build directories it does NOT scan a file written in-process by
    the Python interpreter (verified: write_text / os.write / fsync all go
    undetected in a SwiftPM .build dir, while a shell redirect is caught in ~1s).
    Writing through /bin/sh sidesteps that and mirrors a real on-disk drop.
    The content is passed via the environment to avoid any quoting pitfalls.
    """
    subprocess.run(
        ["/bin/sh", "-c", 'printf "%s" "$EICAR_CONTENT" > "$1"', "sh", str(path)],
        env={**os.environ, "EICAR_CONTENT": EICAR_STRING},
        check=True,
        timeout=10,
    )


def eicar_probe(target_dir: Path, timeout: int = 30, poll: float = 1.0) -> EicarResult:
    """Like :func:`eicar_detected` but returns detail and leaves the file in place.

    Useful for diagnostics: the caller can inspect whether the file survived and
    how the threat count moved. Note: RTP only reliably scans paths it monitors —
    per-user temp dirs (``/private/var/folders``) are not, so probe under $HOME.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    count_before = threat_count()
    path = target_dir / f"eicar_{int(time.time())}.txt"

    try:
        _write_eicar(path)
    except subprocess.CalledProcessError:
        # MDE blocked the write at the filesystem level — that is a detection.
        return EicarResult(True, path, count_before, count_before, False, 0.0)

    elapsed = 0.0
    while elapsed < timeout:
        count_now = threat_count()
        if count_now > count_before:
            return EicarResult(True, path, count_before, count_now, path.exists(), elapsed)
        if not path.exists():
            return EicarResult(True, path, count_before, count_now, False, elapsed)
        time.sleep(poll)
        elapsed += poll

    return EicarResult(False, path, count_before, threat_count(), path.exists(), elapsed)


# ── Build timing ─────────────────────────────────────────────────────────

@dataclass
class BuildMetrics:
    """What a single timed build cost — wall-clock time and MDE scanning CPU."""
    elapsed: float
    mde_cpu: Optional[float]


def timed_build(
    cmd: List[str],
    cwd: Path,
    post_build: Optional[Callable[[], None]] = None,
) -> BuildMetrics:
    """Run a build in cwd and return rich metrics. Raises on failure.

    Captures two things for the build window:
      * wall-clock elapsed seconds (noisy — thermal/cache dependent),
      * average MDE daemon CPU% — the in-window scanning-load signal that drops
        as exclusions and then profiles take effect.

    If ``post_build`` is given, it runs *inside* the timed/CPU-monitored window
    after a successful build (e.g. install + launch the built app on a
    simulator), so its scan-load is part of the same measurement each phase.

    Output is streamed live to the console (not captured) so the user can watch
    the build progress. On failure the build's own output is already on screen,
    so the raised error stays terse.
    """
    print(f"\n$ {' '.join(cmd)}   (in {cwd})", flush=True)
    start = time.perf_counter()
    with _CpuMonitor() as cpu:
        result = subprocess.run(cmd, cwd=cwd, check=False)
        if result.returncode == 0 and post_build is not None:
            post_build()
    elapsed = time.perf_counter() - start
    cpu_avg = cpu.average

    cpu_txt = f"{cpu_avg:.1f}% MDE CPU" if cpu_avg is not None else "CPU n/a"
    print(f"  ↳ exit {result.returncode} in {elapsed:.1f}s  |  {cpu_txt}", flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"build failed ({' '.join(cmd)}) rc={result.returncode} — see build output above"
        )
    return BuildMetrics(elapsed, cpu_avg)
