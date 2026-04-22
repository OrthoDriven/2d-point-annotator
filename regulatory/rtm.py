#!/usr/bin/env python3

import json
from collections import defaultdict

import yaml

# Load canonical requirements
with open("regulatory/requirements.yaml") as f:
    requirements = yaml.safe_load(f)

# Load test results
with open("regulatory/report.json") as f:
    report = json.load(f)

# Index test results by requirement ID
covered = defaultdict(list)
for test in report["tests"]:
    reqs = list(dict.fromkeys(test.get("metadata", {}).get("requirements", [])))
    for req_id in reqs:
        covered[req_id].append(
            {
                "test": test["nodeid"],
                "outcome": test["outcome"],
            }
        )

# Build RTM by walking the canonical list
rtm = []
for req in requirements:
    req_id = req["id"]
    tests = covered.get(req_id, [])
    outcomes = {t["outcome"] for t in tests}

    if not tests:
        status = "untested"
    elif "failed" in outcomes or "error" in outcomes:
        status = "failed"
    else:
        status = "verified"

    rtm.append(
        {
            "id": req_id,
            "title": req["title"],
            "status": status,
            "tests": tests,
        }
    )

with open("regulatory/rtm.json", "w") as f:
    json.dump(rtm, f, indent=2)

# Print summary
for entry in rtm:
    flag = {"verified": "✓", "failed": "✗", "untested": "?"}.get(entry["status"], "?")
    print(f"  {flag} {entry['id']}: {entry['title'][:60]} ({entry['status']})")
