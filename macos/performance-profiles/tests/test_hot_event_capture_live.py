from __future__ import annotations

import json
from pathlib import Path

import pytest

import mde


@pytest.mark.integration
def test_hot_event_capture_live_smoke(require_sudo, tmp_path: Path):
    """Live smoke test: run hot-event capture briefly and validate output shape.

    This intentionally executes the real mdatp diagnostic command (no mocks)
    to verify capture, parsing, and top-source extraction end-to-end.
    """
    out = tmp_path / "hot_event_live.json"
    samples = mde.capture_hot_event_sources(
        duration_seconds=2.0,
        output_path=out,
        interval_seconds=0.5,
    )

    assert out.exists(), "capture did not create output file"
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["snapshot_count"] == samples
    assert data["snapshot_count"] >= 1, "expected at least one parsed snapshot"
    assert isinstance(data.get("snapshots"), list)

    latest = data["snapshots"][-1]
    assert "total_events" in latest
    assert "processed_events" in latest
    assert "urgent_events" in latest
    assert "sources" in latest and isinstance(latest["sources"], list)

    # top_hot_event_sources should match the latest snapshot ordering by count.
    top = data.get("top_hot_event_sources", [])
    print(f"hot-event report: {out}")
    if top:
        print("top hot event sources (latest snapshot):")
        for row in top[:10]:
            print(
                f"  {row.get('count', 0):>6} | {row.get('signing_id', '')} | "
                f"{row.get('team_id', '')} | {row.get('path', '')}"
            )
    else:
        print("top hot event sources: none in latest snapshot")

    if top:
        counts = [row["count"] for row in top]
        assert counts == sorted(counts, reverse=True)
        assert all("path" in row for row in top)
