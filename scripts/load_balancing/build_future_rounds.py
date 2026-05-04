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


def get_unique_count(
    overrides: dict[str, dict],
    ann: str,
    round_num: int,
    default: int,
) -> int:
    """
    Look up per-annotator, per-round unique image count.

    Priority:
    1. annotator_overrides[ann]['unique_r{N}'] (round-specific)
    2. annotator_overrides[ann]['unique'] (all rounds)
    3. default unique_per_person from config
    """
    ann_overrides = overrides.get(ann, {})

    # Round-specific override
    round_key = f"unique_r{round_num}"
    if round_key in ann_overrides:
        return int(ann_overrides[round_key])

    # General override for this annotator
    if "unique" in ann_overrides:
        return int(ann_overrides["unique"])

    return default


def get_multiplier(
    overrides: dict[str, dict],
    ann: str,
) -> float:
    """
    Get the global multiplier for an annotator.

    If set, all counts (unique, shared, intra) are multiplied by this value.
    Default: 1.0 (no change)
    """
    ann_overrides = overrides.get(ann, {})
    return float(ann_overrides.get("multiplier", 1.0))

    return default


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
    annotator_overrides: dict[str, dict] | None = None,
):
    rng = random.Random(seed)
    pool = sorted(future_pool)
    rng.shuffle(pool)

    if annotator_overrides is None:
        annotator_overrides = {}

    rounds = []
    pool_offset = 0
    current_history = {ann: set(h) for ann, h in annotator_history.items()}

    round_num = 2
    while True:
        remaining = len(pool) - pool_offset

        # Get per-annotator counts for this round (applying multiplier)
        unique_counts = {}
        shared_counts = {}
        intra_counts = {}
        for ann in annotators:
            mult = get_multiplier(annotator_overrides, ann)
            base_unique = get_unique_count(annotator_overrides, ann, round_num, unique_per_person)
            unique_counts[ann] = max(1, round(base_unique * mult))
            shared_counts[ann] = max(1, round(round_shared_count * mult))
            intra_counts[ann] = max(1, round(intra_per_person * mult))

        max_unique = max(unique_counts.values()) if unique_counts else unique_per_person

        if remaining < round_shared_count + len(annotators):
            break

        # Shared pool is the same for everyone — capped annotators see a subset
        shared_pool = pool[pool_offset : pool_offset + round_shared_count]
        pool_offset += round_shared_count

        # Calculate unique allocation: capped annotators get their cap, rest divided among uncapped
        available_for_unique = remaining - round_shared_count
        capped_total = 0
        uncapped_count = 0
        for ann in annotators:
            if unique_counts[ann] < max_unique:
                capped_total += unique_counts[ann]
            else:
                uncapped_count += 1

        if uncapped_count > 0:
            uncapped_available = available_for_unique - capped_total
            uncapped_per_person = min(max_unique, uncapped_available // uncapped_count)
        else:
            uncapped_per_person = max_unique

        if uncapped_per_person <= 0 and capped_total == 0:
            break

        round_assignments = {}
        for ann in annotators:
            # Each annotator gets a subset of the shared pool
            r_shared = shared_counts[ann]
            shared_chunk = shared_pool[:r_shared]

            # Capped annotators get their cap, uncapped get uncapped_per_person
            if unique_counts[ann] < max_unique:
                r_unique = unique_counts[ann]
            else:
                r_unique = uncapped_per_person

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

            r_intra = intra_counts[ann]
            if len(repeat_source) >= r_intra:
                intra_chunk = rng.sample(repeat_source, r_intra)
            else:
                intra_chunk = list(repeat_source)

            intra_from_own_history = [img for img in intra_chunk if img in current_history[ann]]

            records = [{"image_path": img, "role": "shared"} for img in shared_chunk]
            records += [{"image_path": img, "role": "unique"} for img in unique_chunk]
            if repeat_role:
                records += [{"image_path": img, "role": repeat_role} for img in intra_chunk]
            rng.shuffle(records)
            round_assignments[ann] = records

            current_history[ann].update(unique_chunk)
            current_history[ann].update(shared_chunk)

        rounds.append({
            "round_num": round_num,
            "assignments": round_assignments,
        })
        round_num += 1

    leftover = pool[pool_offset:]
    if leftover and rounds:
        last = rounds[-1]

        # Get the unique counts for the last round (hard cap)
        last_unique_caps = {}
        for ann in annotators:
            last_unique_caps[ann] = get_unique_count(
                annotator_overrides, ann, last["round_num"], unique_per_person
            )

        # Count how many unique each annotator already has in this round
        current_unique_counts = {}
        for ann in annotators:
            current_unique_counts[ann] = len([
                r for r in last["assignments"][ann] if r["role"] == "unique"
            ])

        # Distribute leftover only to annotators who haven't hit their cap
        remaining_annotators = []
        for i, ann in enumerate(annotators):
            room = last_unique_caps[ann] - current_unique_counts[ann]
            if room > 0:
                remaining_annotators.append((i, ann, room))

        if remaining_annotators and leftover:
            # Distribute proportionally to room available
            total_room = sum(r[2] for r in remaining_annotators)
            allocated = 0
            for idx, (i, ann, room) in enumerate(remaining_annotators):
                if idx == len(remaining_annotators) - 1:
                    chunk_size = len(leftover) - allocated
                else:
                    chunk_size = round(len(leftover) * room / total_room)
                # Cap at available room
                chunk_size = min(chunk_size, room)
                chunk = leftover[allocated:allocated + chunk_size]
                last["assignments"][ann] += [{"image_path": img, "role": "unique"} for img in chunk]
                current_history[ann].update(chunk)
                allocated += chunk_size

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
    annotator_overrides = config.get("annotator_overrides", {})

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
        annotator_overrides=annotator_overrides,
    )

    print(f"\nRounds generated: {len(rounds)}")
    print(f"Default per annotator per round: {unique_per_person} unique + {round_shared_count} shared + {intra_per_person} intra")
    if annotator_overrides:
        print(f"Annotator overrides: {', '.join(annotator_overrides.keys())}")
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
