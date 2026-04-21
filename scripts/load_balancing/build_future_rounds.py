#!/usr/bin/env python3
"""Build Round 2+ assignments for all 5 annotators.

Reads ONLY from fix_round_1 outputs (never overwrites them).
Writes per-annotator assignment JSONs and a schema-compliant summary
with correct inter-rater and per-annotator intra-rater labeling.

Usage:
    pixi run python scripts/load_balancing/build_future_rounds.py
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from config_loader import load_config


def load_round1_data(summary_path: Path, backup_summary_path: Path):
    data = json.loads(summary_path.read_text())
    r1_round = data["rounds"][0]
    round_images = set(r1_round["round_images"])

    annotator_history: dict[str, set[str]] = {}
    output_dir = summary_path.parent
    for group_info in data["group_mapping"].values():
        ann = group_info["annotator"]
        path = output_dir / group_info["file"]
        if path.exists():
            ann_data = json.loads(path.read_text())
            annotator_history[ann] = {img["image_path"] for img in ann_data["images"]}
        else:
            annotator_history[ann] = set()

    bs = json.loads(backup_summary_path.read_text())
    all_images = sorted(bs["image_membership"].keys())

    shared_pool_images = r1_round.get("shared_pool_images", [])

    return round_images, annotator_history, shared_pool_images, all_images


def generate_rounds(
    future_pool: list[str],
    round1_shared: list[str],
    annotator_history: dict[str, set[str]],
    annotators: list[str],
    round_shared_count: int,
    unique_per_person: int,
    intra_per_person: int,
    seed: int,
):
    rng = random.Random(seed)
    pool = sorted(future_pool)
    rng.shuffle(pool)

    rounds = []
    pool_offset = 0
    current_history = {ann: set(h) for ann, h in annotator_history.items()}

    round_num = 2
    while True:
        remaining = len(pool) - pool_offset

        if remaining < round_shared_count + len(annotators):
            break

        r_shared = min(round_shared_count, remaining)
        r_unique = min(unique_per_person, (remaining - r_shared) // len(annotators))

        if r_unique == 0:
            break

        shared_images = pool[pool_offset : pool_offset + r_shared]
        pool_offset += r_shared

        round_assignments = {}
        for ann in annotators:
            unique_chunk = pool[pool_offset : pool_offset + r_unique]
            pool_offset += r_unique

            if current_history[ann]:
                repeat_source = sorted(current_history[ann])
                repeat_role = "intra"
            elif round1_shared:
                repeat_source = sorted(round1_shared)
                repeat_role = "calibration"
            else:
                repeat_source = []
                repeat_role = None

            if len(repeat_source) >= intra_per_person:
                intra_chunk = rng.sample(repeat_source, intra_per_person)
            else:
                intra_chunk = list(repeat_source)

            intra_from_own_history = [img for img in intra_chunk if img in current_history[ann]]

            records = [{"image_path": img, "role": "shared"} for img in shared_images]
            records += [{"image_path": img, "role": "unique"} for img in unique_chunk]
            if repeat_role:
                records += [{"image_path": img, "role": repeat_role} for img in intra_chunk]
            rng.shuffle(records)
            round_assignments[ann] = records

            current_history[ann].update(unique_chunk)
            current_history[ann].update(shared_images)

        rounds.append({
            "round_num": round_num,
            "assignments": round_assignments,
        })
        round_num += 1

    leftover = pool[pool_offset:]
    if leftover and rounds:
        last = rounds[-1]
        leftover_shared = leftover[:min(len(leftover), round_shared_count)]
        leftover_unique = leftover[len(leftover_shared):]

        chunks = [[] for _ in annotators]
        for i, img in enumerate(leftover_unique):
            chunks[i % len(annotators)].append(img)

        for i, ann in enumerate(annotators):
            last["assignments"][ann] += [{"image_path": img, "role": "shared"} for img in leftover_shared]
            last["assignments"][ann] += [{"image_path": img, "role": "unique"} for img in chunks[i]]
            current_history[ann].update(leftover_shared)
            current_history[ann].update(chunks[i])

    return rounds


def _by_role(records, role):
    return [rec["image_path"] for rec in records if rec["role"] == role]


def build_summary(
    rounds: list[dict],
    annotators: list[str],
    annotator_history: dict[str, set[str]],
    total_images: int,
    round1_universe_size: int,
    prefix: str,
    produced_files: list[str],
    round_shared_count: int,
    unique_per_person: int,
    intra_per_person: int,
    seed: int,
) -> dict:
    per_annotator_seen = {ann: set(h) for ann, h in annotator_history.items()}
    round_summaries = []

    for r in rounds:
        r_num = r["round_num"]
        assignments = r["assignments"]

        image_membership = defaultdict(list)
        for ann, recs in assignments.items():
            for rec in recs:
                image_membership[rec["image_path"]].append(ann)

        shared_by_group = {ann: _by_role(assignments[ann], "shared") for ann in annotators}
        unique_by_group = {ann: _by_role(assignments[ann], "unique") for ann in annotators}
        intra_by_group = {ann: _by_role(assignments[ann], "intra") for ann in annotators}
        calibration_by_group = {ann: _by_role(assignments[ann], "calibration") for ann in annotators}

        truly_new_by_group = defaultdict(list)
        prior_union = set().union(*per_annotator_seen.values()) if per_annotator_seen else set()

        for ann in annotators:
            for img in unique_by_group[ann]:
                if img not in per_annotator_seen[ann]:
                    truly_new_by_group[ann].append(img)

        membership_histogram = defaultdict(int)
        total_shared_assignments = 0
        for img, groups in image_membership.items():
            membership_histogram[len(groups)] += 1
            if len(groups) > 1:
                total_shared_assignments += len(groups)

        round_all_images = set(img for recs in assignments.values() for img in [r["image_path"] for r in recs])
        round_images = sorted(round_all_images - prior_union)

        designed_shared_count = len(shared_by_group[annotators[0]]) if annotators else 0

        round_summaries.append({
            "round": r_num,
            "total_original_images_in_round": len(round_images),
            "copying_enabled": True,
            "initial_group_sizes": {ann: len(truly_new_by_group[ann]) for ann in annotators},
            "final_group_sizes": {ann: len(assignments[ann]) for ann in annotators},
            "unique_counts_per_group": {ann: len(unique_by_group[ann]) for ann in annotators},
            "shared_counts_per_group": {ann: len(shared_by_group[ann]) for ann in annotators},
            "calibration_counts_per_group": {ann: len(calibration_by_group[ann]) for ann in annotators},
            "designed_shared_count": designed_shared_count,
            "unique_by_group": {ann: sorted(unique_by_group[ann]) for ann in annotators},
            "shared_by_group": {ann: sorted(shared_by_group[ann]) for ann in annotators},
            "calibration_by_group": {ann: sorted(calibration_by_group[ann]) for ann in annotators},
            "image_membership": {img: sorted(groups) for img, groups in sorted(image_membership.items())},
            "membership_histogram": dict(sorted(membership_histogram.items())),
            "round_images": round_images,
            "global_accounting": {
                "sum_initial_group_sizes": sum(len(truly_new_by_group[ann]) for ann in annotators),
                "sum_final_group_sizes": sum(len(assignments[ann]) for ann in annotators),
                "sum_unique_counts": sum(len(unique_by_group[ann]) for ann in annotators),
                "total_shared_assignments": total_shared_assignments,
            },
            "intra_rater_repeats": {ann: len(intra_by_group.get(ann, [])) for ann in annotators},
            "intra_rater_images": {ann: sorted(intra_by_group.get(ann, [])) for ann in annotators},
            "inter_rater_shared_count": designed_shared_count,
        })

        for ann in annotators:
            per_annotator_seen[ann].update(img for rec in assignments[ann] for img in [rec["image_path"]])

    return {
        "total_original_images": total_images,
        "num_rounds": len(round_summaries),
        "num_groups_per_round": len(annotators),
        "round_shared_count": round_shared_count,
        "unique_per_person": unique_per_person,
        "intra_per_person": intra_per_person,
        "seed": seed,
        "rounds": round_summaries,
        "files": produced_files,
    }


def main():
    parser = argparse.ArgumentParser(description="Build Round 2+ with 65/25/10 logic")
    parser.add_argument("--config", default="scripts/load_balancing/configs/build_future_rounds.yaml")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    seed = args.seed if args.seed is not None else config.get("seed", 5678)

    output_dir = Path(config.get("output_dir", "data"))
    round1_summary_path = Path(config.get("round1_summary", "data/fluoro-r1_round1_summary.json"))
    annotators = config.get("annotators", ["scott", "andrew", "mark", "paris", "sonia"])
    round_shared_count = config.get("round_shared_count", 25)
    unique_per_person = config.get("unique_per_person", 65)
    intra_per_person = config.get("intra_per_person", 10)
    prefix = config.get("prefix", "fluoro-r2")

    backup_summary_path = Path(config.get("backup_summary", "data/remote_backups/fluoro-r1_summary.json"))
    r1_universe, annotator_history, r1_shared, all_images = load_round1_data(round1_summary_path, backup_summary_path)
    future_pool = [img for img in all_images if img not in r1_universe]

    for ann in annotators:
        if ann not in annotator_history:
            annotator_history[ann] = set()

    print(f"Total images: {len(all_images)}")
    print(f"Round 1 universe: {len(r1_universe)}")
    print(f"Future pool: {len(future_pool)}")
    print(f"Annotators ({len(annotators)}): {', '.join(annotators)}")

    rounds = generate_rounds(
        future_pool, r1_shared, annotator_history, annotators,
        round_shared_count, unique_per_person, intra_per_person, seed,
    )

    print(f"\nRounds generated: {len(rounds)}")
    print(f"Per annotator per round: {unique_per_person} unique + {round_shared_count} shared + {intra_per_person} intra = {unique_per_person + round_shared_count + intra_per_person}")
    for r in rounds:
        sizes = {ann: len(imgs) for ann, imgs in r["assignments"].items()}
        print(f"  Round {r['round_num']}: {sizes}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    template_path = output_dir / "fluoro-r1_round1_andrew.json"
    if not template_path.exists():
        template_path = next(output_dir.glob("fluoro-r1_round1_*.json"))
    template = json.loads(template_path.read_text())

    output_dir.mkdir(parents=True, exist_ok=True)
    produced_files = []
    for r in rounds:
        r_num = r["round_num"]
        for ann, recs in r["assignments"].items():
            records = [{
                "image_path": rec["image_path"],
                "image_flag": False,
                "view": None,
                "image_direction": None,
                "annotations": {},
            } for rec in recs]

            out_path = output_dir / f"{prefix}_round{r_num}_{ann}.json"
            out_path.write_text(json.dumps({
                "landmarks": template["landmarks"],
                "views": template["views"],
                "images": records,
            }, indent=2))
            produced_files.append(str(out_path))
            print(f"  Wrote {out_path} ({len(recs)} images)")

    summary = build_summary(
        rounds, annotators, annotator_history, len(all_images), len(r1_universe),
        prefix, produced_files, round_shared_count, unique_per_person, intra_per_person,
        seed,
    )
    summary_path = output_dir / f"{prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"  Wrote {summary_path}")


if __name__ == "__main__":
    main()
