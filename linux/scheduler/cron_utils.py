#!/usr/bin/env python3

import os
import subprocess


class CronError(Exception):
    pass


def get_current_crontab():
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        result = subprocess.run(
            ["crontab", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as error:
        raise CronError(f"Failed to list the current crontab: {error}") from error

    if result.returncode == 0:
        return result.stdout

    error_message = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode == 1 and error_message.lower().startswith("no crontab for "):
        return b""

    raise CronError(
        f"Failed to list the current crontab: {error_message or 'unknown error'}"
    )


def write_crontab_backup(backup_path, current_crontab):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    try:
        file_descriptor = os.open(backup_path, flags, 0o600)
    except OSError as error:
        raise CronError(f"Failed to create backup '{backup_path}': {error}") from error

    try:
        with os.fdopen(file_descriptor, "wb") as backup_file:
            os.fchmod(backup_file.fileno(), 0o600)
            backup_file.write(current_crontab)
            backup_file.flush()
            os.fsync(backup_file.fileno())
    except OSError as error:
        cleanup_error = None
        try:
            os.unlink(backup_path)
        except FileNotFoundError:
            pass
        except OSError as unlink_error:
            cleanup_error = unlink_error

        error_message = f"Failed to write backup '{backup_path}': {error}"
        if cleanup_error:
            error_message += (
                f"; failed to remove incomplete backup '{backup_path}': "
                f"{cleanup_error}"
            )
        raise CronError(error_message) from error


def append_cron_entry(current_crontab, cron_expression):
    separator = b"" if not current_crontab or current_crontab.endswith(b"\n") else b"\n"
    return (
        current_crontab
        + separator
        + cron_expression.encode("utf-8")
        + b"\n"
    )


def install_crontab(crontab_content):
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        result = subprocess.run(
            ["crontab", "-"],
            input=crontab_content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as error:
        raise CronError(f"Failed to install the updated crontab: {error}") from error

    if result.returncode != 0:
        error_message = result.stderr.decode("utf-8", errors="replace").strip()
        raise CronError(
            f"Failed to install the updated crontab: "
            f"{error_message or 'unknown error'}"
        )


def add_cron_entry(cron_expression, backup_path=None):
    current_crontab = get_current_crontab()
    if backup_path is not None:
        write_crontab_backup(backup_path, current_crontab)

    install_crontab(append_cron_entry(current_crontab, cron_expression))
