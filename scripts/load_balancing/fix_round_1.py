#!/usr/bin/env python3
"""Post-hoc Round 1 assignment builder.

Reads ONLY from immutable backup data in data/remote_backups/.
Writes per-annotator assignment JSONs and a schema-compliant summary.

Usage:
    pixi run python scripts/load_balancing/fix_round_1.py --dry-run
    pixi run python scripts/load_balancing/fix_round_1.py
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from config_loader import load_config

FOLDER_MAPPING = {"scott": "SAB", "andrew": "ajj"}


def load_backup(annotator: str, backup_dir: Path, prefix: str, folder_mapping: dict | None = None) -> dict | None:
    mapping = folder_mapping or FOLDER_MAPPING
    folder = mapping.get(annotator, annotator)
    folder_path = backup_dir / folder
    path = folder_path / f"{prefix}_{annotator}.json"
    if not folder_path.exists():
        print(f"  [info] no backup folder for {annotator}: {folder_path}")
        return None
    if not path.exists():
        print(f"  [info] backup folder exists but no file: {path}")
        return None
    return json.loads(path.read_text())


def load_all_images_from_backup_summary(summary_path: Path) -> list[str]:
    data = json.loads(summary_path.read_text())
    return sorted(data["image_membership"].keys())


def get_annotated_images(data: dict) -> set[str]:
    return {img["image_path"] for img in data["images"] if img.get("view") is not None}


def build_assignments(
    annotators: list[str],
    annotated_per_user: dict[str, set[str]],
    all_images: list[str],
    shared_pool_size: int,
    min_total_n: int,
    rng: random.Random,
) -> tuple[dict[str, list[str]], list[str]]:
    andrew_annotated = annotated_per_user.get("andrew", set())
    assignments: dict[str, list[str]] = {"andrew": sorted(andrew_annotated)}

    andrew_sorted = sorted(andrew_annotated)
    shared_pool = rng.sample(andrew_sorted, shared_pool_size)

    all_assigned = set(andrew_annotated)
    for ann in annotators:
        if ann != "andrew":
            all_assigned |= annotated_per_user.get(ann, set())

    fallback_pool = sorted(img for img in all_images if img not in all_assigned)
    rng.shuffle(fallback_pool)
    fallback_idx = 0

    for annotator in annotators:
        if annotator == "andrew":
            continue

        my_annotated = annotated_per_user.get(annotator, set())
        assignment_set = set(my_annotated) | set(shared_pool)

        # min_total_n is a floor; preserved work may exceed it
        still_needed = min_total_n - len(assignment_set)
        if still_needed > 0:
            while still_needed > 0 and fallback_idx < len(fallback_pool):
                img = fallback_pool[fallback_idx]
                fallback_idx += 1
                if img not in assignment_set:
                    assignment_set.add(img)
                    still_needed -= 1

        annotated = sorted(assignment_set & my_annotated)
        unannotated = sorted(assignment_set - my_annotated)
        assignments[annotator] = annotated + unannotated

    return assignments, shared_pool


def merge_annotations(image_paths: list[str], existing_data: dict | None) -> list[dict]:
    by_path: dict[str, dict] = {}
    if existing_data:
        for img in existing_data.get("images", []):
            by_path[img["image_path"]] = img

    return [
        by_path.get(path, {
            "image_path": path,
            "image_flag": False,
            "view": None,
            "image_direction": None,
            "annotations": {},
        })
        for path in image_paths
    ]


def write_annotator_json(image_records: list[dict], template_source: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps({
        "landmarks": template_source["landmarks"],
        "views": template_source["views"],
        "images": image_records,
    }, indent=2))


def build_summary(
    annotators: list[str],
    assignments: dict[str, list[str]],
    annotated_per_user: dict[str, set[str]],
    andrew_annotated: set[str],
    shared_pool: list[str],
    shared_pool_size: int,
    output_prefix: str,
    total_images: int,
    seed: int,
) -> dict:
    round1_universe = sorted(set().union(*assignments.values()))

    n = len(annotators)
    group_names = [f"group_{i+1}" for i in range(n)]
    ann_to_group = {ann: f"group_{i+1}" for i, ann in enumerate(annotators)}
    group_to_ann = {f"group_{i+1}": ann for i, ann in enumerate(annotators)}

    image_membership = defaultdict(list)
    for ann, imgs in assignments.items():
        g = ann_to_group[ann]
        for img in imgs:
            image_membership[img].append(g)

    unique_by_group = {g: [] for g in group_names}
    shared_by_group = {g: [] for g in group_names}
    for img, groups in image_membership.items():
        if len(groups) == 1:
            unique_by_group[groups[0]].append(img)
        else:
            for g in groups:
                shared_by_group[g].append(img)

    unique_counts = {g: len(v) for g, v in unique_by_group.items()}
    shared_counts = {g: len(v) for g, v in shared_by_group.items()}

    membership_histogram = defaultdict(int)
    total_shared_assignments = 0
    for img, groups in image_membership.items():
        membership_histogram[len(groups)] += 1
        if len(groups) > 1:
            total_shared_assignments += len(groups)

    group_mapping = {
        g: {"file": f"{output_prefix}_round1_{group_to_ann[g]}.json", "annotator": group_to_ann[g]}
        for g in group_names
    }

    per_annotator = {}
    for ann in annotators:
        ann_set = set(assignments[ann])
        my_annotated = annotated_per_user.get(ann, set())
        per_annotator[ann] = {
            "total_assigned": len(assignments[ann]),
            "already_annotated": len(my_annotated),
            "from_andrew_set": len(ann_set & andrew_annotated),
            "brand_new": len(ann_set - my_annotated - andrew_annotated),
        }

    round_data = {
        "round": 1,
        "total_original_images_in_round": len(round1_universe),
        "copying_enabled": True,
        "share_m": shared_pool_size,
        "initial_group_sizes": {ann_to_group[ann]: len(annotated_per_user.get(ann, set())) for ann in annotators},
        "final_group_sizes": {ann_to_group[ann]: len(assignments[ann]) for ann in annotators},
        "unique_counts_per_group": unique_counts,
        "shared_counts_per_group": shared_counts,
        "sampled_by_group": {ann_to_group["andrew"]: sorted(shared_pool)},
        "copied_into_group": {g: sorted(shared_pool) if g != ann_to_group["andrew"] else [] for g in group_names},
        "unique_by_group": {g: sorted(v) for g, v in unique_by_group.items()},
        "shared_by_group": {g: sorted(v) for g, v in shared_by_group.items()},
        "image_membership": {img: sorted(groups) for img, groups in sorted(image_membership.items())},
        "membership_histogram": dict(sorted(membership_histogram.items())),
        "round_images": round1_universe,
        "global_accounting": {
            "sum_initial_group_sizes": sum(len(annotated_per_user.get(ann, set())) for ann in annotators),
            "sum_final_group_sizes": sum(len(assignments[ann]) for ann in annotators),
            "sum_unique_counts": sum(unique_counts.values()),
            "total_shared_assignments": total_shared_assignments,
        },
        "intra_rater_repeats": {},
        "intra_rater_images": {},
        "inter_rater_shared_count": len([img for img, groups in image_membership.items() if len(groups) > 1]),
        "study_phase": "round1_postmortem",
        "shared_pool_images": sorted(shared_pool),
        "per_annotator": per_annotator,
    }

    return {
        "total_original_images": total_images,
        "num_rounds": 1,
        "num_groups_per_round": n,
        "share_m": shared_pool_size,
        "seed": seed,
        "round_sizes": {"round_1": len(round1_universe)},
        "rounds": [round_data],
        "group_mapping": group_mapping,
    }


def main():
    parser = argparse.ArgumentParser(description="Post-hoc Round 1 assignment builder")
    parser.add_argument("--config", default="scripts/load_balancing/configs/fix_round_1.yaml")
    parser.add_argument("--backup-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    seed = args.seed if args.seed is not None else config.get("seed", 1234)
    backup_dir = Path(args.backup_dir) if args.backup_dir else Path(config.get("backup_dir", "data/remote_backups"))
    output_dir = Path(args.output_dir) if args.output_dir else Path(config.get("output_dir", "data"))
    backup_summary = Path(config.get("backup_summary", "data/remote_backups/fluoro-r1_summary.json"))

    annotators = config.get("annotators", ["scott", "andrew", "mark", "paris"])
    shared_pool_size = config.get("shared_pool_size", 20)
    if "min_total_n" in config:
        min_total_n = config["min_total_n"]
    elif "target_n" in config:
        print("[warn] config key 'target_n' is deprecated, use 'min_total_n'")
        min_total_n = config["target_n"]
    else:
        min_total_n = 100
    prefix = config.get("prefix", "fluoro-r1")
    folder_mapping = config.get("folder_mapping")

    rng = random.Random(seed)
    all_images = load_all_images_from_backup_summary(backup_summary)
    print(f"Total image pool (from backup summary): {len(all_images)}")

    raw_data: dict[str, dict | None] = {}
    annotated_per_user: dict[str, set[str]] = {}
    for ann in annotators:
        data = load_backup(ann, backup_dir, prefix, folder_mapping)
        raw_data[ann] = data
        annotated_per_user[ann] = get_annotated_images(data) if data else set()
        print(f"  {ann}: {len(annotated_per_user[ann])} annotated")

    andrew_annotated = annotated_per_user.get("andrew", set())
    print(f"\nAndrew's set (source for shared pool): {len(andrew_annotated)}")

    assignments, shared_pool = build_assignments(
        annotators, annotated_per_user, all_images, shared_pool_size, min_total_n, rng,
    )

    print(f"\nShared reliability pool ({shared_pool_size} images):")
    for img in sorted(shared_pool):
        print(f"    {img}")

    print()
    for ann in annotators:
        imgs = assignments[ann]
        my_annotated = annotated_per_user.get(ann, set())
        preserved = len(my_annotated & set(imgs))
        added = len(set(imgs) - my_annotated)
        from_andrew = len(set(imgs) & andrew_annotated)
        brand_new = len(set(imgs) - my_annotated - andrew_annotated)
        shared_in_set = len(set(imgs) & set(shared_pool))
        print(
            f"  {ann}: {len(imgs)} total  "
            f"({preserved} preserved, {added} added, "
            f"{from_andrew} from-andrew, {brand_new} brand-new, "
            f"{shared_in_set} in-shared)"
        )

    template_source = next((d for d in raw_data.values() if d is not None), None)
    if template_source is None:
        raise RuntimeError("No backup data found")

    templates = [(ann, d) for ann, d in raw_data.items() if d is not None]
    if len(templates) > 1:
        ref_ann, ref = templates[0]
        for ann, d in templates[1:]:
            if d["landmarks"] != ref["landmarks"] or d["views"] != ref["views"]:
                raise RuntimeError(
                    f"Backup template drift: {ann} landmarks/views differ from {ref_ann}. "
                    f"Investigate before regenerating."
                )

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    for ann in annotators:
        records = merge_annotations(assignments[ann], raw_data[ann])
        out_path = output_dir / f"{prefix}_round1_{ann}.json"
        write_annotator_json(records, template_source, out_path)
        print(f"  Wrote {out_path}")

    summary = build_summary(
        annotators, assignments, annotated_per_user, andrew_annotated,
        shared_pool, shared_pool_size, prefix, len(all_images), seed,
    )
    summary_path = output_dir / f"{prefix}_round1_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"  Wrote {summary_path}")


if __name__ == "__main__":
    main()
