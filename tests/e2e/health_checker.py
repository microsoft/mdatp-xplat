#!/usr/bin/env python3
"""health_checker.py.

Parses output from 'mdatp health --output json' and provides structured
access to installation health and onboarding status.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class HealthStatus:
    """Parsed health status from mdatp health command."""

    daemon_running: bool
    real_time_protection: bool
    onboarded: bool
    definitions_updated: bool
    engine_version: Optional[str]
    definitions_version: Optional[str]
    product_expiration: Optional[str]
    licenses: Optional[Dict] = None
    raw_output: Optional[Dict] = None

    def is_healthy(self) -> bool:
        """Check if MDE is in a healthy state (full check including definitions)."""
        return self.daemon_running and self.onboarded and self.definitions_updated


class HealthChecker:
    """Query and parse MDE health status."""

    def __init__(self):
        """Initialize health checker."""
        pass

    @staticmethod
    def get_health_json() -> Optional[Dict]:
        """Execute 'mdatp health --output json' and return parsed JSON.

        Returns:
            Parsed JSON dict or None if command fails

        """
        try:
            result = subprocess.run(
                ["mdatp", "health", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,  # Don't raise on non-zero exit
            )

            if result.returncode != 0:
                pass

            if result.stdout:
                return json.loads(result.stdout)
            return None
        except subprocess.TimeoutExpired:
            return None
        except json.JSONDecodeError:
            return None
        except FileNotFoundError:
            return None
        except Exception:
            return None

    @staticmethod
    def parse_health(health_json: Dict) -> HealthStatus:
        """Parse health JSON into HealthStatus object.

        Args:
            health_json: Parsed JSON from 'mdatp health --output json'

        Returns:
            HealthStatus object with extracted fields

        """
        # The health JSON structure uses different field names than expected
        # Key fields: healthy, licensed, definitionsStatus, realTimeProtectionEnabled

        # Daemon is running if we get valid health JSON with healthy field
        daemon_running = health_json.get("healthy", False)

        # Real-time protection status
        rtp_field = health_json.get("realTimeProtectionEnabled", {})
        if isinstance(rtp_field, dict):
            rtp_enabled = rtp_field.get("value", False)
        else:
            rtp_enabled = rtp_field is True

        # Onboarding status - uses "licensed" field
        onboarded = health_json.get("licensed", False)

        # Definitions status - check definitionsStatus.$type == "upToDate"
        def_status = health_json.get("definitionsStatus", {})
        if isinstance(def_status, dict):
            definitions_updated = def_status.get("$type") == "upToDate"
        else:
            definitions_updated = False

        # Versions
        engine_version = health_json.get("engineVersion")
        definitions_version = health_json.get("definitionsVersion")
        product_expiration = health_json.get("productExpiration")

        # Licenses (optional)
        licenses = health_json.get("licenses", {})

        return HealthStatus(
            daemon_running=daemon_running,
            real_time_protection=rtp_enabled,
            onboarded=onboarded,
            definitions_updated=definitions_updated,
            engine_version=engine_version,
            definitions_version=definitions_version,
            product_expiration=product_expiration,
            licenses=licenses,
            raw_output=health_json,
        )

    @staticmethod
    def check_health() -> Optional[HealthStatus]:
        """Check MDE health status.

        Returns:
            HealthStatus object or None if check fails

        """
        health_json = HealthChecker.get_health_json()
        if health_json is None:
            return None

        return HealthChecker.parse_health(health_json)

    @staticmethod
    def wait_for_health(max_attempts: int = 30, interval_sec: int = 5) -> Optional[HealthStatus]:
        """Poll health status until it reports healthy or max attempts reached.

        Args:
            max_attempts: Maximum number of attempts
            interval_sec: Seconds between attempts

        Returns:
            HealthStatus object when healthy, or None if timeout

        """
        health = None
        for attempt in range(1, max_attempts + 1):
            health = HealthChecker.check_health()

            if health and health.is_healthy():
                return health

            if attempt < max_attempts:
                time.sleep(interval_sec)
            elif health:
                pass

        return health


def main():
    """CLI for testing health checker."""
    health = HealthChecker.check_health()

    if not health:
        sys.exit(1)



if __name__ == "__main__":
    main()
