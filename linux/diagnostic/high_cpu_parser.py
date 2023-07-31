import argparse
import json
import sys

parser = argparse.ArgumentParser(description="Process scan measures")
parser.add_argument("--group", action="store_true", help="Whether to group the results by process name")
parser.add_argument("--top", type=int, help="Limits the number of results")

args = parser.parse_args()
group = args.group
top = args.top or sys.maxsize

vals = json.load(sys.stdin)["counters"]

if group:
    groups = {}

    for v in vals:
        name = v["name"]

        if "path" in v:
            path = v["path"]

        cnt = int(v["totalFilesScanned"])
        if name not in groups:
            groups[name] = [cnt, path]
        else:
            groups[name][0] = groups[name][0] + cnt

    lines = sorted(groups, key=lambda k: groups[k], reverse=True)
    for k in lines[:top]:
        print("%s\t%d" % (k, groups[k][0]))

else:
    lines = sorted(vals, key=lambda k: int(k['totalFilesScanned']), reverse=True)
    for v in lines[:top]:
        if int(v["totalFilesScanned"]) != 0:
            print("%s\t%s\t%s\t%s" % (v["id"], v["name"], v["totalFilesScanned"], v["path"]))
