"""
Xcode build demo scenario.

Shows the impact of MDE performance profiles on a Swift/Xcode build process.
"""

from pathlib import Path
from typing import Optional

from .base import ScenarioConfig
from .profiled_build import ProfiledBuildScenario


class XcodeScenario(ProfiledBuildScenario):
    """Demo scenario for building microsoft/fluentui-apple."""

    def __init__(self, repo_path: Optional[Path] = None):
        config = ScenarioConfig(
            name="FluentUI Apple Xcode Build Demo",
            description="Demo showing MDE impact on Xcode/Swift builds",
            repo_url="https://github.com/microsoft/fluentui-apple.git",
            repo_path=repo_path or (Path.home() / "demo" / "fluentui-apple"),
            build_command="swift build -c release",
            profiles=["xcode", "xcode-ide-tree", "git"],
            estimated_duration_minutes=20,
        )
        super().__init__(
            config=config,
            build_command=["swift", "build", "-c", "release"],
            tool_checks=[["git", "--version"], ["swift", "--version"]],
            repo_validation_file="Package.swift",
            clone_in_timed_phases=True,
        )
