#!/usr/bin/env python3
"""Schedule MDE scans via cron.

This script creates cron jobs for scheduled Microsoft Defender for Endpoint
antivirus scans on Linux systems.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import NoReturn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class CronError(Exception):
    """Exception raised for cron-related errors."""

    pass


def backup_cron_jobs(debug: bool = False) -> Path:
    """Backup current cron jobs to a timestamped file.

    Args:
        debug: If True, only print the command without executing.

    Returns:
        Path to the backup file.

    Raises:
        CronError: If backup fails.
    """
    today = datetime.today().date()
    formatted_date = today.strftime("%Y%m%d")
    backup_path = Path(f"/tmp/cron_schedule_scan_backup_{formatted_date}")

    if debug:
        logger.debug("Would backup cron to: %s", backup_path)
        return backup_path

    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )

        # crontab -l returns 1 if no crontab exists, which is fine
        if result.returncode == 0:
            backup_path.write_text(result.stdout)
            logger.info("Cron jobs backed up to %s", backup_path)
        else:
            logger.info("No existing crontab to backup")

        return backup_path

    except OSError as e:
        raise CronError(f"Failed to backup cron jobs: {e}") from e


def create_cron_job(
    minute: str = "*",
    hour: str = "2",
    day_of_month: str = "*",
    month: str = "*",
    day_of_week: str = "*",
    command: str = "/bin/mdatp scan quick > /tmp/mdatp_scheduled_scan.log",
    debug: bool = False,
) -> None:
    """Create a cron job for scheduled scanning.

    Args:
        minute: Cron minute field.
        hour: Cron hour field.
        day_of_month: Cron day of month field.
        month: Cron month field.
        day_of_week: Cron day of week field.
        command: Command to execute.
        debug: If True, only print what would be done.

    Raises:
        CronError: If cron job creation fails.
    """
    cron_expression = f"{minute} {hour} {day_of_month} {month} {day_of_week} {command}"

    if debug:
        logger.debug("Would create cron job: %s", cron_expression)
        return

    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )

        existing_crontab = result.stdout if result.returncode == 0 else ""

        # Check if job already exists
        if cron_expression in existing_crontab:
            logger.info("Cron job already exists")
            return

        # Create new crontab content
        new_crontab = existing_crontab.rstrip() + "\n" + cron_expression + "\n"

        # Write to temp file and load
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".cron", delete=False
        ) as temp_file:
            temp_file.write(new_crontab)
            temp_path = Path(temp_file.name)

        try:
            subprocess.run(
                ["crontab", str(temp_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Cron job added successfully: %s", cron_expression)
        finally:
            temp_path.unlink(missing_ok=True)

    except subprocess.CalledProcessError as e:
        raise CronError(f"Failed to create cron job: {e.stderr}") from e
    except OSError as e:
        raise CronError(f"Failed to create cron job: {e}") from e


def main() -> NoReturn:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a cron job for scheduled MDE virus scans."
    )
    parser.add_argument(
        "-H",
        "--hour",
        type=int,
        default=2,
        choices=range(0, 24),
        metavar="HOUR",
        help="Hour of the day (0-23). Default: 2 (2am)",
    )
    parser.add_argument(
        "-D",
        "--day",
        choices=["*", "0", "1", "2", "3", "4", "5", "6"],
        default="*",
        help="Day of week (0=Sunday, 6=Saturday). Default: * (everyday)",
    )
    parser.add_argument(
        "-S",
        "--scan",
        dest="scan_type",
        choices=["quick", "full"],
        default="quick",
        help="Type of scan to run. Default: quick",
    )
    parser.add_argument(
        "-L",
        "--log",
        dest="log_file",
        default="/tmp/mdatp_scheduled_scan.log",
        help="Log file location for scan output. Default: /tmp/mdatp_scheduled_scan.log",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Debug mode (print commands without executing)",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Hour: %s, Day: %s, Scan: %s", args.hour, args.day, args.scan_type)

    try:
        cmd_string = f"/bin/mdatp scan {args.scan_type} > {args.log_file}"

        backup_cron_jobs(args.debug)
        create_cron_job(
            hour=str(args.hour),
            day_of_week=args.day,
            command=cmd_string,
            debug=args.debug,
        )
        sys.exit(0)

    except CronError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
