#!/usr/bin/env python3

import argparse
import sys

from cron_utils import CronError, add_cron_entry


def create_cron_job(
    minute="*",
    hour="2",
    day_of_month="*",
    month="*",
    day_of_week="6",
    command="",
    debug=False,
    backup_path=None,
):
    cron_expression = (
        f"{minute} {hour} {day_of_month} {month} {day_of_week} {command}"
    )

    if debug:
        print(f"[d] cron_expression: {cron_expression}")
        print("[d] list_command: crontab -l")
        if backup_path is not None:
            print(f"[d] backup_path: {backup_path}")
        print("[d] install_command: crontab -")
    else:
        add_cron_entry(cron_expression, backup_path)
        print(f"Cron job added successfully: {cron_expression}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="This script creates a cron job that will perform MDE package updates on the desired schedule.")
    parser.add_argument("-H", "--hour",
        action="store",
        dest="hour",
        type=int,
        default=2,
        choices=range(0,24),
        help="A number that represents the hour of the day: 0-23 (0 being midnight). Default: 2(2am)")
    parser.add_argument("-D", "--day",
        action="store",
        dest="day",
        choices=["0","1","2","3","4","5","6"],
        default=6,
        help="A number that represents the day of the week: 0 => Sunday, 6 => Saturday. Everyday ('*') is not allowed as checking for updates daily is not recommended. Default: 6(SAT). ")
    parser.add_argument("-O", "--os",
        choices=["RHEL", "SLES", "DEB"],
        action="store",
        default="DEB",
        dest="os",
        help="Linux Distribution. Default: DEB")
    parser.add_argument("-L", "--log",
        action="store",
        dest="log_file",
        default="/tmp/mdatp_update_job.log",
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
        update_dict = {"RHEL":"yum update mdatp -y",
                       "SLES":"zypper update mdatp",
                       "DEB":"apt install --only-upgrade mdatp"}

        cmd_string = f"sudo {update_dict[args.os]} >> {args.log_file}"
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
        print(f"[!] schedule_update script failed: {error}", file=sys.stderr)
        sys.exit(1)
