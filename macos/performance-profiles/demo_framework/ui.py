"""
UI utilities for spinners, progress, and formatted output.
"""

import time
import sys
import threading
from typing import Optional, Callable


class Spinner:
    """Simple spinner for long-running operations."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = ""):
        self.message = message
        self.running = False
        self.thread = None

    def start(self) -> None:
        """Start the spinner."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop the spinner."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def _spin(self) -> None:
        """Spin animation loop."""
        frame_idx = 0
        while self.running:
            frame = self.FRAMES[frame_idx % len(self.FRAMES)]
            elapsed = time.time() - self.start_time
            msg = f"{frame} {self.message} ({elapsed:.0f}s)"
            sys.stdout.write(f"\r{msg:<80}")
            sys.stdout.flush()
            time.sleep(0.1)
            frame_idx += 1

    def __enter__(self):
        self.start_time = time.time()
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def run_with_spinner(message: str, func: Callable, *args, **kwargs):
    """Run a function with spinner, return result."""
    with Spinner(message) as spinner:
        result = func(*args, **kwargs)
    return result


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'─' * 70}")
    print(f"📋 {title}")
    print(f"{'─' * 70}\n")


def print_step(step: int, message: str) -> None:
    """Print a step indicator."""
    print(f"   {step}. {message}")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"   ✅ {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"   ❌ {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    print(f"   ⚠️  {message}")


def print_info(message: str) -> None:
    """Print info message."""
    print(f"   ℹ️  {message}")
