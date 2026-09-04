#!/usr/bin/env python3

import os
import subprocess


class CronError(Exception):
    pass


def _remove_incomplete_backup(backup_path):
    try:
        os.unlink(backup_path)
    except FileNotFoundError:
        return None
    except OSError as error:
        return error
    return None


def _validate_cron_expression(cron_expression):
    if "\n" in cron_expression or "\r" in cron_expression:
        raise CronError("Cron expression must contain exactly one line.")


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
        backup_file = os.fdopen(file_descriptor, "wb")
    except OSError as error:
        cleanup_errors = []
        try:
            os.close(file_descriptor)
        except OSError as close_error:
            cleanup_errors.append(f"failed to close backup: {close_error}")

        unlink_error = _remove_incomplete_backup(backup_path)
        if unlink_error:
            cleanup_errors.append(
                f"failed to remove incomplete backup '{backup_path}': {unlink_error}"
            )

        error_message = f"Failed to open backup '{backup_path}': {error}"
        if cleanup_errors:
            error_message += "; " + "; ".join(cleanup_errors)
        raise CronError(error_message) from error

    try:
        with backup_file:
            os.fchmod(backup_file.fileno(), 0o600)
            backup_file.write(current_crontab)
            backup_file.flush()
            os.fsync(backup_file.fileno())
    except OSError as error:
        cleanup_error = _remove_incomplete_backup(backup_path)

        error_message = f"Failed to write backup '{backup_path}': {error}"
        if cleanup_error:
            error_message += (
                f"; failed to remove incomplete backup '{backup_path}': "
                f"{cleanup_error}"
            )
        raise CronError(error_message) from error


def append_cron_entry(current_crontab, cron_expression):
    _validate_cron_expression(cron_expression)

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
    _validate_cron_expression(cron_expression)
    current_crontab = get_current_crontab()
    updated_crontab = append_cron_entry(current_crontab, cron_expression)
    if backup_path is not None:
        write_crontab_backup(backup_path, current_crontab)

    install_crontab(updated_crontab)
