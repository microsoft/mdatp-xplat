"""Tests for orchestrator module."""

import pytest
from pathlib import Path
from demo_framework.orchestrator import DemoOrchestrator, PhaseStatus, CommandRunner


class TestDemoOrchestrator:
    """Test demo orchestrator."""

    def test_create_orchestrator(self):
        """Test creating an orchestrator."""
        orch = DemoOrchestrator("test demo")
        assert orch.name == "test demo"
        assert orch.results_dir.exists()

    def test_add_phases(self):
        """Test adding phases."""
        orch = DemoOrchestrator("test")
        
        def phase1():
            return "phase 1 output"
        
        orch.add_phase("Phase 1", phase1)
        assert len(orch.phases) == 1
        assert orch.phases[0][0] == "Phase 1"

    def test_run_single_phase(self):
        """Test running a single phase."""
        orch = DemoOrchestrator("test")
        
        def phase():
            return "output"
        
        orch.add_phase("Test Phase", phase)
        success = orch.run()
        
        assert success
        assert len(orch.results) == 1
        assert orch.results[0].status == PhaseStatus.COMPLETED

    def test_run_failing_phase(self):
        """Test handling a failing phase."""
        orch = DemoOrchestrator("test")
        
        def phase():
            raise Exception("Phase failed")
        
        orch.add_phase("Failing Phase", phase)
        success = orch.run()
        
        assert not success
        assert len(orch.results) == 1
        assert orch.results[0].status == PhaseStatus.FAILED

    def test_summary(self):
        """Test getting execution summary."""
        orch = DemoOrchestrator("test")
        
        orch.add_phase("Phase 1", lambda: "output 1")
        orch.add_phase("Phase 2", lambda: "output 2")
        
        orch.run()
        summary = orch.summary()
        
        assert summary["name"] == "test"
        assert summary["total_phases"] == 2
        assert summary["completed"] == 2
        assert summary["failed"] == 0


class TestCommandRunner:
    """Test command runner."""

    def test_run_successful_command(self):
        """Test running a successful command."""
        code, stdout, stderr = CommandRunner.run(
            ["echo", "hello"],
            capture=True
        )
        assert code == 0
        assert "hello" in stdout

    def test_run_failing_command(self):
        """Test running a failing command."""
        code, stdout, stderr = CommandRunner.run(
            ["sh", "-c", "exit 1"],
            capture=True
        )
        assert code == 1

    def test_run_command_timeout(self):
        """Test command timeout."""
        code, stdout, stderr = CommandRunner.run(
            ["sleep", "10"],
            capture=True,
            timeout=1
        )
        assert code == 124  # timeout exit code
