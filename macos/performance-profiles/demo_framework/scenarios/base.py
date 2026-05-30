"""
Base scenario class for demo scenarios.

Scenarios are extensible demo templates that can be customized for different
use cases (VS Code, Xcode, macOS native, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ..orchestrator import DemoOrchestrator


@dataclass
class ScenarioConfig:
    """Configuration for a demo scenario."""
    name: str
    description: str
    repo_url: Optional[str] = None
    repo_path: Optional[Path] = None
    build_command: Optional[str] = None
    clean_command: Optional[str] = None
    profiles: list = None
    estimated_duration_minutes: int = 30


class DemoScenario(ABC):
    """Base class for demo scenarios."""

    def __init__(self, config: ScenarioConfig):
        self.config = config
        self.orchestrator = DemoOrchestrator(config.name, config.repo_path)

    @abstractmethod
    def setup(self) -> bool:
        """Prepare for demo. Return True if successful."""
        pass

    @abstractmethod
    def build_baseline(self) -> bool:
        """Run baseline build without profiles."""
        pass

    @abstractmethod
    def apply_profiles(self) -> bool:
        """Apply performance profiles."""
        pass

    @abstractmethod
    def build_optimized(self) -> bool:
        """Run optimized build with profiles."""
        pass

    @abstractmethod
    def analyze_results(self) -> bool:
        """Collect diagnostics and analyze impact."""
        pass

    def run(self, resume_from: Optional[int] = None) -> bool:
        """Execute the full demo scenario."""
        self.orchestrator.cache_sudo()
        
        return self.orchestrator.run(resume_from=resume_from)

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return self.orchestrator.summary()
