"""The 3-way demo, expressed once.

Each scenario test supplies its build command, profiles, and the build-output
directory where EICAR is dropped, then calls :func:`three_way_demo`. The story
is identical across scenarios:

  1. Baseline       — no profiles, no exclusions → fast-enough build, EICAR caught.
  2. AV exclusions  — exclude the build dir      → fast build, EICAR MISSED (the gap).
  3. Perf profiles  — apply profiles             → fast build, EICAR caught (no gap).

Before any of that, :func:`verify_clean_state` proves the endpoint is in a known
state (RTP on, no exclusions, no demo profiles) so a stray leftover can never be
mistaken for a real result. Every phase prints exactly what RTP did.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import mde


@dataclass
class Scenario:
    name: str
    build_cmd: List[str]
    eicar_subdir: str
    profiles: List[str]
    # Build/artifact dirs to AV-exclude — defaults to just the EICAR dir.
    exclusion_subdirs: List[str] = field(default_factory=list)
    # Absolute (non-repo) paths to AV-exclude during the exclusions phase, e.g.
    # the iOS Simulator data tree that an install/launch step writes into. These
    # support ~ expansion and exist so the exclusions phase covers the *same*
    # trees the perf profiles do (otherwise the comparison is unfair).
    exclusion_abs_paths: List[str] = field(default_factory=list)
    # Optional callback run *inside* the timed/CPU-monitored build window after a
    # successful build — e.g. install + launch the built app on a simulator, so
    # that workflow's scan-load is part of the same measurement every phase.
    post_build: Optional[Callable[[Path], None]] = None
    # Optional callback run *outside* the timed build window before each phase's
    # build, e.g. dependency restore/setup that must happen after cleaning but
    # should not be counted in the build-time/CPU measurement.
    pre_build: Optional[Callable[[Path], None]] = None
    # Dirs/files to remove before each timed build. Defaults to the excluded
    # dirs, but can be set explicitly when some excluded dir must NOT be deleted
    # between builds (e.g. node_modules: excluded from scanning, but installed once).
    clean_paths: List[str] = field(default_factory=list)
    # Glob patterns (relative to the repo) to remove before each build, e.g.
    # "*.tsbuildinfo". node_modules is skipped while matching to stay fast.
    clean_globs: List[str] = field(default_factory=list)

    @property
    def exclusion_dirs_rel(self) -> List[str]:
        """Repo-relative dirs that get AV-excluded during the exclusions phase."""
        return self.exclusion_subdirs or [self.eicar_subdir]

    def exclusion_targets(self, repo: Path) -> List[Path]:
        """Every absolute path AV-excluded during the exclusions phase — the
        repo-relative build dirs plus any absolute (e.g. simulator) trees."""
        rel = [repo / r for r in self.exclusion_dirs_rel]
        absolute = [Path(p).expanduser() for p in self.exclusion_abs_paths]
        return rel + absolute

    @property
    def clean_targets(self) -> List[str]:
        """Repo-relative paths to remove before each timed build."""
        if self.clean_paths:
            return self.clean_paths
        dirs = list(dict.fromkeys([self.eicar_subdir, *self.exclusion_subdirs]))
        return [d for d in dirs if d]


def _clean(repo: Path, scenario: Scenario) -> None:
    """Remove build artifacts so each timed build is a full rebuild."""
    for rel in scenario.clean_targets:
        # Safety guard: never remove the scenario repository root.
        if rel in {"", "."}:
            continue
        target = repo / rel
        if target.resolve() == repo.resolve():
            continue
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    for pattern in scenario.clean_globs:
        for match in repo.rglob(pattern):
            if "node_modules" in match.parts:
                continue
            try:
                if match.is_dir():
                    shutil.rmtree(match, ignore_errors=True)
                else:
                    match.unlink()
            except OSError:
                pass


def _step(msg: str) -> None:
    print(f"\n--- {msg} ---", flush=True)


def _report_state(repo: Path, scenario: Scenario) -> None:
    """Print exactly what MDE has enabled right now — the ground truth each phase
    runs against, so a surprising build number can be traced to real state."""
    rtp = mde.rtp_enabled()
    exclusions = mde.list_exclusion_paths()
    applied = mde.list_applied_profiles()
    scenario_excl = {str(p).rstrip("/") for p in scenario.exclusion_targets(repo)}
    live_scenario_excl = sorted(p for p in exclusions if p.rstrip("/") in scenario_excl)
    relevant_profiles = sorted(set(applied) & set(scenario.profiles))
    print(f"  [state] RTP enabled        : {rtp}", flush=True)
    print(f"  [state] scenario exclusions: {live_scenario_excl or 'none'}", flush=True)
    print(f"  [state] all exclusions     : {exclusions or 'none'}", flush=True)
    print(f"  [state] scenario profiles  : {relevant_profiles or 'none'}", flush=True)
    print(f"  [state] all profiles       : {applied or 'none'}", flush=True)


def assert_state(repo: Path, scenario: Scenario, *, excluded: bool, profiled: bool) -> None:
    """Assert the live MDE state matches what this phase requires.

    Run immediately before each build so every phase proves its own preconditions:
    every excluded dir is/ isn't AV-excluded, and the scenario profiles are/ aren't
    applied. Checking *all* excluded dirs (not just the EICAR dir) catches the case
    where some artifact dir silently failed to be excluded — which would make the
    exclusions phase look no different from baseline.
    """
    exclusions = {p.rstrip("/") for p in mde.list_exclusion_paths()}
    applied = mde.list_applied_profiles()
    scenario_dirs = [str(p).rstrip("/") for p in scenario.exclusion_targets(repo)]
    missing = [d for d in scenario_dirs if d not in exclusions]
    present = [d for d in scenario_dirs if d in exclusions]
    is_profiled = bool(set(applied) & set(scenario.profiles))

    if excluded and missing:
        raise AssertionError(
            f"expected all scenario dirs excluded but these are not: {missing} "
            f"(live exclusions={sorted(exclusions)})"
        )
    if not excluded and present:
        raise AssertionError(
            f"expected no scenario dirs excluded but these are: {present} "
            f"(live exclusions={sorted(exclusions)})"
        )
    if is_profiled != profiled:
        raise AssertionError(
            f"expected profiles applied={profiled} but got {is_profiled} (applied={applied})"
        )


def verify_clean_state(repo: Path, scenario: Scenario) -> None:
    """Prove and enforce a known-good starting state. Fails loudly otherwise."""
    _step(f"[{scenario.name}] Verifying endpoint state")

    if not mde.rtp_enabled():
        raise AssertionError("real-time protection is OFF — enable it before running the demo")

    # Defensively clear any leftover exclusions on this scenario's dirs.
    for target in scenario.exclusion_targets(repo):
        mde.remove_exclusion(target)
    # Defensively clear any scenario profiles so baseline truly has none.
    mde.remove_profiles(scenario.profiles)

    exclusions = mde.list_exclusion_paths()
    profiles = mde.list_applied_profiles()

    scenario_dirs = {str(p).rstrip("/") for p in scenario.exclusion_targets(repo)}
    leftover = [p for p in exclusions if p.rstrip("/") in scenario_dirs]
    if leftover:
        raise AssertionError(f"could not clear leftover exclusions: {leftover}")
    if set(profiles) & set(scenario.profiles):
        raise AssertionError(
            f"could not clear leftover demo profiles: {sorted(set(profiles) & set(scenario.profiles))}"
        )


def three_way_demo(repo: Path, scenario: Scenario, report) -> None:
    eicar_dir = repo / scenario.eicar_subdir
    exclusion_dirs = scenario.exclusion_targets(repo)
    post = (lambda: scenario.post_build(repo)) if scenario.post_build else None
    pre = (lambda: scenario.pre_build(repo)) if scenario.pre_build else None

    verify_clean_state(repo, scenario)

    def measure(target: Path) -> mde.EicarResult:
        r = mde.eicar_probe(target)
        if r.path.exists():
            r.path.unlink()
        return r

    # ── Phase 1: Baseline (no profiles, no exclusions) ──────────────────
    _step(f"[{scenario.name}] Baseline build (no profiles, no exclusions)")
    _clean(repo, scenario)
    assert_state(repo, scenario, excluded=False, profiled=False)
    _report_state(repo, scenario)
    if pre:
        pre()
    baseline_m = mde.timed_build(scenario.build_cmd, repo, post_build=post)
    baseline = measure(eicar_dir)

    # ── Phase 2: AV folder exclusions (the security gap) ────────────────
    _step(f"[{scenario.name}] AV exclusions build")
    for d in exclusion_dirs:
        mde.add_exclusion(d)
    try:
        _clean(repo, scenario)
        assert_state(repo, scenario, excluded=True, profiled=False)
        _report_state(repo, scenario)
        if pre:
            pre()
        exclusions_m = mde.timed_build(scenario.build_cmd, repo, post_build=post)
        exclusions = measure(eicar_dir)
    finally:
        for d in exclusion_dirs:
            mde.remove_exclusion(d)

    # ── Phase 3: Performance profiles (speed without the gap) ───────────
    _step(f"[{scenario.name}] Performance profiles build")
    mde.apply_profiles(scenario.profiles)
    try:
        _clean(repo, scenario)
        assert_state(repo, scenario, excluded=False, profiled=True)
        _report_state(repo, scenario)
        if pre:
            pre()
        profiles_m = mde.timed_build(scenario.build_cmd, repo, post_build=post)
        profiles = measure(eicar_dir)
    finally:
        mde.remove_profiles(scenario.profiles)

    report.record(
        scenario.name, baseline_m, exclusions_m, profiles_m,
        baseline.detected, exclusions.detected, profiles.detected,
        applied_profiles=list(scenario.profiles),
        added_exclusions=[d.name for d in exclusion_dirs],
    )

    # The point of the demo, as assertions — each with the captured evidence:
    assert baseline.detected, f"RTP should catch EICAR with no profiles/exclusions ({baseline})"
    assert not exclusions.detected, f"AV folder exclusion should create a detection gap ({exclusions})"
    assert profiles.detected, f"Performance profiles must keep RTP effective ({profiles})"
