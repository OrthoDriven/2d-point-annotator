#!/usr/bin/env python3

import json
from collections import defaultdict

report = json.load(open(".report.json"))

rtm = defaultdict(lambda: {"requirement": "", "tests": [], "status": "untested"})

for test in report["tests"]:
    reqs = list(dict.fromkeys(test.get("metadata", {}).get("requirements", [])))
    for req in reqs:
        rtm[req]["requirement"] = req
        rtm[req]["tests"].append({"test": test["nodeid"], "outcome": test["outcome"]})

# resolve status
for req, entry in rtm.items():
    outcomes = {t["outcome"] for t in entry["tests"]}
    entry["status"] = "failed" if "failed" in outcomes else "verified"

output = sorted(rtm.values(), key=lambda x: x["requirement"])
json.dump(output, open("rtm.json", "w"), indent=2)
print(f"RTM written: {len(output)} requirements")
