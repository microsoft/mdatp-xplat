import argparse
import json
import sys

parser = argparse.ArgumentParser(description="Process scan measures")
parser.add_argument("--group", type=bool, help="Whether to group the results by process name")
parser.add_argument("--top", type=int, help="Limits the number of results")

args = parser.parse_args()
group = args.group
top = args.top or sys.maxsize

vals = json.load(sys.stdin)["counters"]

if group:
    groups = {}

    for v in vals:
        name = v["name"]
        cnt = int(v["total_files_scanned"])
        if name not in groups:
            groups[name] = cnt
        else:
            groups[name] = groups[name] + cnt

    lines = sorted(groups, key=lambda k: groups[k], reverse=True)
    for k in lines[:top]:
        print("%s\t%d" % (k, groups[k]))
        
else:
    lines = sorted(vals, key=lambda k: int(k['total_files_scanned']), reverse=True)
    for v in lines[:top]:
        if int(v["total_files_scanned"]) != 0:
            print("%s\t%s\t%s" % (v["id"], v["name"], v["total_files_scanned"]))
