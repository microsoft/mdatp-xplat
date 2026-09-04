#!/usr/bin/env python3

import argparse
import sys

from cron_utils import CronError, add_cron_entry


def create_cron_job(
    minute="*",
    hour="2",
    day_of_month="*",
    month="*",
    day_of_week="*",
    command="/bin/mdatp scan quick > /tmp/mdatp_scheduled_scan.log",
    debug=False,
    backup_path=None,
):
    cron_expression = (
        f"{minute} {hour} {day_of_month} {month} {day_of_week} {command}"
    )

    if debug:
        print(f"[d] cron_expression: {cron_expression}")
        print("[d] list_command: crontab -l")
        if backup_path:
            print(f"[d] backup_path: {backup_path}")
        print("[d] install_command: crontab -")
    else:
        add_cron_entry(cron_expression, backup_path)
        print(f"Cron job added successfully: {cron_expression}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="This script creates a cron job that will perform virus scans on the desired schedule.")
    parser.add_argument("-H", "--hour",
        action="store",
        dest="hour",
        type=int,
        default=2,
        choices=range(0,24),
        help="A Number representing the hour of the day: 0-23 (0 being midnight). Default: 2 (2am)")
    parser.add_argument("-D", "--day",
        action="store",
        dest="day",
        choices=["*", "0", "1", "2", "3", "4", "5", "6"],
        default="*",
        help="A Number representing the day of the week: 0 => Sunday, 6 => Saturday. Default: * (everyday)")
    parser.add_argument("-S", "--scan",
        action="store",
        dest="scan_type",
        choices=["quick", "full"],
        default="quick",
        help="Type of scan to run ('quick' or 'full').")
    parser.add_argument("-L", "--log",
        action="store",
        dest="log_file",
        default="/tmp/mdatp_scheduled_scan.log",
        help="Log file location for output.")
    parser.add_argument("-d", "--debug",
        action="store_true",
        dest="debug",
        default=False,
        help="dump parameters")
    parser.add_argument("--backup",
        action="store",
        dest="backup_path",
        help="Save the current crontab to a new file before installing the updated crontab.")

    try:
        args = parser.parse_args()
        cmd_string = f"/bin/mdatp scan {args.scan_type} > {args.log_file}"
        if args.debug:
            print(f"[d] Hour: {args.hour} Day: {args.day} Cmd: {cmd_string}")

        create_cron_job(
            hour=args.hour,
            day_of_week=args.day,
            command=cmd_string,
            debug=args.debug,
            backup_path=args.backup_path,
        )
    except KeyboardInterrupt:
        sys.exit(130)
    except CronError as error:
        print(f"[!] schedule_scan script failed: {error}", file=sys.stderr)
        sys.exit(1)
