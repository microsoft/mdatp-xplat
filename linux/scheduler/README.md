# Scripts

Two scripts are available to help with creating cron tasks related to MDE.

The scripts modify the crontab of the user who runs them. Sudo is not required
for ordinary per-user scheduling. Running a script with sudo intentionally
modifies root's crontab.

Both scripts preserve existing entries and append a new entry each time they
run, including when an identical entry already exists. They install the updated
crontab through standard input using `crontab -`; this is supported by Cronie
and Debian/Vixie-derived cron implementations and does not depend on the Linux
kernel version.

Use `--backup PATH` to save the previous crontab before installing the new
entry. The backup is created as a new file with permissions `0600`. For safety,
the command fails without modifying the crontab if the path already exists or
the backup cannot be written. Choose a path in a directory trusted by the user
running the script. Restore a backup manually with `crontab PATH`.

## schedule_scan.py

This script creates a cron job that will perform virus scans on the desired schedule.

### Usage 

`$ python3 schedule_scan.py [-h] [-H {0-23}] [-D {*,0-6}] [-S {quick,full}] [-L LOG_FILE] [--backup PATH] [-d]`

### Options

| Commandline Parameter | Description | Default Value |
| --- | --- | --- |
| -h, --help | show this help message and exit | |
| -H {0-23}, --hour {0-23} | A Number representing the hour of the day: 0-23 (0 being midnight). | 2 (2am) |
| -D {*,0-6}, --day {*,0-6} | A Number representing the day of the week: 0 => Sunday, 6 => Saturday or * to represent every day. | * (everyday) |
| -S {quick,full}, --scan {quick,full} | Type of scan to run ('quick' or 'full'). | quick |
| -L LOG_FILE, --log LOG_FILE | Log file name and location for output. | /tmp/mdatp_scheduled_scan.log |
| --backup PATH | Save the current crontab to a new `0600` file before making changes. | No backup |
| -d, --debug | dump script parameters and print debug statements. No actions will be taken | |

## schedule_update.py

This script creates a cron job that will perform MDE package updates on the desired schedule.

### Usage: 

`$ python3 schedule_update.py [-h] [-H {0-23}] [-D {0-6}] [-O {RHEL,SLES,DEB}] [-L LOG_FILE] [--backup PATH] [-d]`

### Options

| Commandline Parameter | Description | Default Value |
| --- | --- | --- |
| -h, --help | show this help message and exit | |
| -H {0-23}, --hour {0-23} | A number that represents the hour of the day: 0-23 (0 being midnight). | 2 (2am) |
| -D {0-6}, --day {0-6} | A number that represents the day of the week: 0 => Sunday, 6 => Saturday. Everyday ('*') is not allowed as checking for updates daily is not recommended. | 6 (SAT) | 
| -O {RHEL,SLES,DEB}, --os {RHEL,SLES,DEB} | Linux Distribution | DEB |
| -L LOG_FILE, --log LOG_FILE | Log file location for output. | /tmp/mdatp_update_job.log |
| --backup PATH | Save the current crontab to a new `0600` file before making changes. | No backup |
| -d, --debug | dump parameters | |
