#!/usr/bin/env python3
"""Verify assignment logic by reading the actual generated data.

Reads from:
  - data/fluoro-r1_round1_summary.json (fix_round_1 output)
  - data/fluoro-r1_round1_{name}.json  (fix_round_1 output)
  - data/fluoro-r2_summary.json        (build_future_rounds output)
  - data/remote_backups/fluoro-r1_summary.json (immutable, for total count)

Usage:
    pixi run python scripts/load_balancing/verify_assignment_logic.py
"""

import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path


def main():
    data_dir = Path("data")

    backup_summary = json.loads((data_dir / "remote_backups" / "fluoro-r1_summary.json").read_text())
    total_images = len(backup_summary["image_membership"])

    r1_summary = json.loads((data_dir / "fluoro-r1_round1_summary.json").read_text())
    r1_round = r1_summary["rounds"][0]

    r1_annotators = [g["annotator"] for g in r1_summary["group_mapping"].values()]
    r1_per_ann = {}
    r1_annotated_per_ann = {}
    for ann in r1_annotators:
        path = data_dir / f"fluoro-r1_round1_{ann}.json"
        ann_data = json.loads(path.read_text())
        r1_per_ann[ann] = {img["image_path"] for img in ann_data["images"]}
        r1_annotated_per_ann[ann] = {img["image_path"] for img in ann_data["images"] if img.get("view") is not None}

    r1_universe = set(r1_round["round_images"])

    backup_annotated = {}
    folder_map = {"scott": "SAB", "andrew": "ajj"}
    for ann in r1_annotators:
        folder = folder_map.get(ann, ann)
        bp = data_dir / "remote_backups" / folder / f"fluoro-r1_{ann}.json"
        if bp.exists():
            bd = json.loads(bp.read_text())
            backup_annotated[ann] = {img["image_path"] for img in bd["images"] if img.get("view") is not None}
        else:
            backup_annotated[ann] = set()

    print("=" * 70)
    print("ROUND 1 — Post-Hoc Load Balancing")
    print("=" * 70)
    print(f"Total image pool: {total_images}")
    print(f"Round 1 universe: {len(r1_universe)} unique images assigned")
    print()

    active = {a: s for a, s in backup_annotated.items() if s}
    for r in [3, 2]:
        for combo in combinations(active.keys(), r):
            overlap = set.intersection(*(active[u] for u in combo))
            if overlap:
                print(f"  Pre-existing overlap {'&'.join(combo)}: {len(overlap)} images")

    shared_pool = set(r1_round.get("shared_pool_images", []))
    print(f"\n  Shared reliability pool: {len(shared_pool)} images (from Andrew's set)")
    print()

    print(f"  {'Annotator':<10} {'Total':>6} {'Preserved':>10} {'New Work':>9} {'Shared':>7}")
    print(f"  {'-'*10} {'-'*6} {'-'*10} {'-'*9} {'-'*7}")
    for ann in r1_annotators:
        total = len(r1_per_ann[ann])
        preserved = len(backup_annotated.get(ann, set()) & r1_per_ann[ann])
        new_work = total - preserved
        in_shared = len(r1_per_ann[ann] & shared_pool)
        print(f"  {ann:<10} {total:>6} {preserved:>10} {new_work:>9} {in_shared:>7}")

    print(f"\n  Sonia excluded from Round 1 (onboarding)")

    r2_summary_path = data_dir / "fluoro-r2_summary.json"
    if not r2_summary_path.exists():
        print("\n[WARN] fluoro-r2_summary.json not found.")
        return

    r2_summary = json.loads(r2_summary_path.read_text())

    print()
    print("=" * 70)
    print("ROUNDS 2+ — 65/25/10 Reliability Model")
    print("=" * 70)

    r2_annotators = ["scott", "andrew", "mark", "paris", "sonia"]

    all_seen = set(r1_universe)
    cumulative_shared = len(shared_pool)

    round_rows = []
    for rd in r2_summary["rounds"]:
        r_num = rd["round"]

        round_all_images = set()
        for ann in r2_annotators:
            path = data_dir / f"fluoro-r2_round{r_num}_{ann}.json"
            if path.exists():
                d = json.loads(path.read_text())
                round_all_images.update(img["image_path"] for img in d["images"])

        new_this_round = round_all_images - all_seen
        all_seen.update(round_all_images)

        inter = rd["inter_rater_shared_count"]
        cumulative_shared += inter

        sample_ann = r2_annotators[0]
        total_per = rd["final_group_sizes"].get(sample_ann, 0)
        intra_sample = rd.get("intra_rater_repeats", {}).get(sample_ann, 0)

        round_rows.append({
            "r_num": r_num,
            "new_in_round": len(new_this_round),
            "inter": inter,
            "intra_sample": intra_sample,
            "total_per": total_per,
            "cumulative_shared": cumulative_shared,
            "cumulative_new": len(all_seen),
            "remaining": total_images - len(all_seen),
        })

    print(f"\n  {'Round':<8} {'New Imgs':>8} {'Shared':>7} {'Intra':>6} {'Per Person':>11} {'Cum.Shared':>11} {'Cum.New':>8} {'Left':>6}")
    print(f"  {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*11} {'-'*11} {'-'*8} {'-'*6}")
    print(f"  {'R1':<8} {len(r1_universe):>8} {len(shared_pool):>7} {'—':>6} {'—':>11} {len(shared_pool):>11} {len(r1_universe):>8} {total_images - len(r1_universe):>6}")
    for row in round_rows:
        print(f"  R{row['r_num']:<7} {row['new_in_round']:>8} {row['inter']:>7} {row['intra_sample']:>6} {row['total_per']:>11} {row['cumulative_shared']:>11} {row['cumulative_new']:>8} {row['remaining']:>6}")

    print()
    print("  Per-round breakdown by annotator:")
    print(f"  {'Round':<8}", end="")
    for ann in r2_annotators:
        print(f" {ann:>10}", end="")
    print()
    print(f"  {'-'*8}", end="")
    for _ in r2_annotators:
        print(f" {'-'*10}", end="")
    print()
    for rd in r2_summary["rounds"]:
        r_num = rd["round"]
        print(f"  R{r_num:<7}", end="")
        for ann in r2_annotators:
            total = rd["final_group_sizes"].get(ann, 0)
            unique = rd["initial_group_sizes"].get(ann, 0)
            shared = rd["shared_counts_per_group"].get(ann, 0)
            intra = rd.get("intra_rater_repeats", {}).get(ann, 0)
            print(f" {unique}+{shared}+{intra}={total:>3}", end="")
        print()

    print()
    print("  Intra-rater QC per annotator per round:")
    print(f"  {'Annotator':<10}", end="")
    for rd in r2_summary["rounds"]:
        print(f" {'R'+str(rd['round']):>6}", end="")
    print()
    print(f"  {'-'*10}", end="")
    for _ in r2_summary["rounds"]:
        print(f" {'-'*6}", end="")
    print()
    for ann in r2_annotators:
        print(f"  {ann:<10}", end="")
        for rd in r2_summary["rounds"]:
            intra = rd.get("intra_rater_repeats", {}).get(ann, 0)
            print(f" {intra:>6}", end="")
        print()

    print()
    print("=" * 70)
    print("LIFETIME TOTALS")
    print("=" * 70)

    print(f"\n  {'Annotator':<10} {'R1':>5} {'R2+ New':>8} {'R2+ Shared':>11} {'R2+ Intra':>10} {'R2+ Work':>9} {'Grand':>7}")
    print(f"  {'-'*10} {'-'*5} {'-'*8} {'-'*11} {'-'*10} {'-'*9} {'-'*7}")
    for ann in r2_annotators:
        r1_total = len(r1_per_ann.get(ann, set()))
        r2_unique = sum(rd["initial_group_sizes"].get(ann, 0) for rd in r2_summary["rounds"])
        r2_shared = sum(rd["shared_counts_per_group"].get(ann, 0) for rd in r2_summary["rounds"])
        r2_intra = sum(rd.get("intra_rater_repeats", {}).get(ann, 0) for rd in r2_summary["rounds"])
        r2_total = sum(rd["final_group_sizes"].get(ann, 0) for rd in r2_summary["rounds"])
        grand = r1_total + r2_total
        print(f"  {ann:<10} {r1_total:>5} {r2_unique:>8} {r2_shared:>11} {r2_intra:>10} {r2_total:>9} {grand:>7}")

    final_cumul_new = len(all_seen)
    print(f"\n  Cumulative inter-rater shared: {cumulative_shared}")
    print(f"  Cumulative unique assigned:    {final_cumul_new} / {total_images}")
    print(f"  Remaining unassigned:          {total_images - final_cumul_new}")


if __name__ == "__main__":
    main()
