"""
Tests that every scenario correctly wires all common parameters through to
the ProfiledBuildScenario base class.
"""

from pathlib import Path

import pytest

from demo_framework.scenarios.android_studio import AndroidStudioScenario
from demo_framework.scenarios.vscode import VSCodeScenario
from demo_framework.scenarios.xcode import XcodeScenario
from demo_framework.scenarios.xcode_simulator import XcodeSimulatorScenario

DEFAULT_ANALYZER_DIR = Path.home() / "demo" / "analyzer" / "XMDEClientAnalyzerBinary"
CUSTOM_ANALYZER_DIR = Path("/custom/analyzer")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vscode(tmp_path, **kwargs):
    return VSCodeScenario(repo_path=tmp_path / "vscode", **kwargs)


def _make_xcode(tmp_path, **kwargs):
    return XcodeScenario(repo_path=tmp_path / "fluentui-apple", **kwargs)


def _make_xcode_sim(tmp_path, **kwargs):
    return XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios", **kwargs)


def _make_android(tmp_path, **kwargs):
    return AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android", **kwargs)


FACTORIES = [_make_vscode, _make_xcode, _make_xcode_sim, _make_android]
FACTORY_IDS = ["vscode", "xcode", "xcode-simulator", "android-studio"]


# ---------------------------------------------------------------------------
# hot_events_analysis_mode
# ---------------------------------------------------------------------------

class TestHotEventsAnalysisMode:
    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_default_is_not_broken(self, tmp_path, factory):
        scenario = factory(tmp_path)
        assert scenario.hot_events_analysis_mode in ("none", "prompt")

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_python_mode(self, tmp_path, factory):
        scenario = factory(tmp_path, hot_events_analysis_mode="python")
        assert scenario.hot_events_analysis_mode == "python"

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_ghcp_mode(self, tmp_path, factory):
        scenario = factory(tmp_path, hot_events_analysis_mode="ghcp")
        assert scenario.hot_events_analysis_mode == "ghcp"

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_both_mode(self, tmp_path, factory):
        scenario = factory(tmp_path, hot_events_analysis_mode="both")
        assert scenario.hot_events_analysis_mode == "both"

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_prompt_mode(self, tmp_path, factory):
        scenario = factory(tmp_path, hot_events_analysis_mode="prompt")
        assert scenario.hot_events_analysis_mode == "prompt"


# ---------------------------------------------------------------------------
# analyzer_dir
# ---------------------------------------------------------------------------

class TestAnalyzerDir:
    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_default_analyzer_dir(self, tmp_path, factory):
        scenario = factory(tmp_path)
        assert scenario.analyzer_dir == DEFAULT_ANALYZER_DIR

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_custom_analyzer_dir(self, tmp_path, factory):
        scenario = factory(tmp_path, analyzer_dir=CUSTOM_ANALYZER_DIR)
        assert scenario.analyzer_dir == CUSTOM_ANALYZER_DIR


# ---------------------------------------------------------------------------
# enable_client_analyzer
# ---------------------------------------------------------------------------

class TestEnableClientAnalyzer:
    def test_vscode_defaults_client_analyzer_on(self, tmp_path):
        scenario = _make_vscode(tmp_path)
        assert scenario.enable_client_analyzer is True

    @pytest.mark.parametrize("factory", [_make_xcode, _make_xcode_sim, _make_android],
                             ids=["xcode", "xcode-simulator", "android-studio"])
    def test_non_vscode_defaults_client_analyzer_off(self, tmp_path, factory):
        scenario = factory(tmp_path)
        assert scenario.enable_client_analyzer is False

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_enable_client_analyzer_true(self, tmp_path, factory):
        scenario = factory(tmp_path, enable_client_analyzer=True)
        assert scenario.enable_client_analyzer is True

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_enable_client_analyzer_false(self, tmp_path, factory):
        scenario = factory(tmp_path, enable_client_analyzer=False)
        assert scenario.enable_client_analyzer is False


# ---------------------------------------------------------------------------
# profile_change_policy
# ---------------------------------------------------------------------------

class TestProfileChangePolicy:
    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_default_profile_change_policy(self, tmp_path, factory):
        scenario = factory(tmp_path)
        assert scenario.profile_change_policy == "prompt"

    @pytest.mark.parametrize("factory,policy", [
        (_make_vscode, "always"),
        (_make_xcode, "never"),
        (_make_xcode_sim, "always"),
        (_make_android, "never"),
    ], ids=["vscode-always", "xcode-never", "xcode-sim-always", "android-never"])
    def test_custom_profile_change_policy(self, tmp_path, factory, policy):
        scenario = factory(tmp_path, profile_change_policy=policy)
        assert scenario.profile_change_policy == policy


# ---------------------------------------------------------------------------
# enable_exclusion_workflow
# ---------------------------------------------------------------------------

class TestEnableExclusionWorkflow:
    def test_vscode_exclusion_follows_client_analyzer_default(self, tmp_path):
        # When enable_exclusion_workflow is None, it mirrors enable_client_analyzer
        scenario = _make_vscode(tmp_path)
        assert scenario.enable_exclusion_workflow == scenario.enable_client_analyzer

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_exclusion_workflow_true(self, tmp_path, factory):
        scenario = factory(tmp_path, enable_exclusion_workflow=True)
        assert scenario.enable_exclusion_workflow is True

    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_explicit_exclusion_workflow_false(self, tmp_path, factory):
        scenario = factory(tmp_path, enable_exclusion_workflow=False)
        assert scenario.enable_exclusion_workflow is False


# ---------------------------------------------------------------------------
# Combination: all overrides together
# ---------------------------------------------------------------------------

class TestAllParamsTogether:
    @pytest.mark.parametrize("factory", FACTORIES, ids=FACTORY_IDS)
    def test_all_params_applied(self, tmp_path, factory):
        scenario = factory(
            tmp_path,
            hot_events_analysis_mode="both",
            analyzer_dir=CUSTOM_ANALYZER_DIR,
            enable_client_analyzer=True,
            enable_exclusion_workflow=False,
            profile_change_policy="always",
        )
        assert scenario.hot_events_analysis_mode == "both"
        assert scenario.analyzer_dir == CUSTOM_ANALYZER_DIR
        assert scenario.enable_client_analyzer is True
        assert scenario.enable_exclusion_workflow is False
        assert scenario.profile_change_policy == "always"
