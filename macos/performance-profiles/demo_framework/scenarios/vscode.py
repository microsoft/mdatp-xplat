"""
VS Code build demo scenario.

Shows the impact of MDE performance profiles on the Microsoft VS Code build process.
"""

from pathlib import Path
from typing import Optional

from .base import ScenarioConfig
from .profiled_build import ProfiledBuildScenario


class VSCodeScenario(ProfiledBuildScenario):
    """Demo scenario for building Microsoft VS Code."""

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        include_install_in_build: bool = False,
        profile_change_policy: str = "prompt",
    ):
        config = ScenarioConfig(
            name="Microsoft VS Code Build Demo",
            description="End-to-end demo showing MDE impact on VS Code compilation",
            repo_url="https://github.com/microsoft/vscode.git",
            repo_path=repo_path or (Path.home() / "demo" / "vscode"),
            build_command="npm run compile",
            profiles=["node", "git", "vscode", "vscode-tree"],
            estimated_duration_minutes=60,
        )
        super().__init__(
            config=config,
            build_command=["npm", "run", "compile"],
            tool_checks=[],
            repo_validation_file=None,
            clone_in_timed_phases=False,
            clone_args=["--depth", "1", "--branch", "1.122.1"],
            install_command=["npm", "install"],
            include_install_in_build=include_install_in_build,
            build_cleanup_paths=["node_modules/.cache", "out", ".build"],
            build_cleanup_globs=["*.tsbuildinfo"],
            default_exclusions=[
                {"type": "folder", "rel": "node_modules"},
                {"type": "folder", "rel": "out"},
                {"type": "folder", "rel": ".build"},
            ],
            eicar_subdir="out",
            enable_resume_checkpoint=True,
            state_file_name=".vscode-demo-state.json",
            profile_change_policy=profile_change_policy,
        )
