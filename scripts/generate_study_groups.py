#!/usr/bin/env python3
"""Generate annotation group files from a study configuration.

Reads data/studies.json and data/datasets.json, resolves the image folder
for the requested study, and calls the existing make_image_group_data
functions to produce per-annotator JSON files and a summary.

The original make_image_group_data.py is imported as a library and
never modified.

Usage:
    python scripts/generate_study_groups.py --study-id fluoro-round-1-reliability
    python scripts/generate_study_groups.py --all
    python scripts/generate_study_groups.py --list
"""

import argparse
import json
import random
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

# Import from sibling scripts directory
sys.path.insert(0, str(SCRIPTS_DIR))
from make_image_group_data import (  # noqa: E402
    apply_cross_group_copying,
    build_summary,
    get_image_files,
    make_json_template,
    rel_display_path,
    split_evenly,
)

# Import dataset config from src/
sys.path.insert(0, str(REPO_ROOT / "src"))
from dataset_config import get_data_dir, load_datasets_config  # noqa: E402


def load_studies_config(path: Path | None = None) -> list[dict]:
    if path is None:
        path = REPO_ROOT / "data" / "studies.json"
    if not path.exists():
        raise FileNotFoundError(f"Studies config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["studies"]


def validate_study(study: dict) -> None:
    required = ["id", "dataset_id", "num_groups", "seed"]
    for key in required:
        if key not in study:
            raise ValueError(
                f"Study '{study.get('id', '?')}' missing required key: {key}"
            )

    if study["num_groups"] <= 0:
        raise ValueError(f"Study '{study['id']}': num_groups must be > 0")

    share_m = study.get("share_m", 0)
    if share_m < 0:
        raise ValueError(f"Study '{study['id']}': share_m must be >= 0")
    if share_m > 0 and study["num_groups"] < 2:
        raise ValueError(f"Study '{study['id']}': share_m requires at least 2 groups")

    names = study.get("annotator_names")
    if names is not None:
        if len(names) != study["num_groups"]:
            raise ValueError(
                f"Study '{study['id']}': annotator_names has {len(names)} entries "
                f"but num_groups is {study['num_groups']}"
            )
        if len(set(names)) != len(names):
            raise ValueError(
                f"Study '{study['id']}': annotator_names contains duplicates"
            )


def resolve_image_folder(study: dict) -> Path:
    """Resolve the dataset_id to an image folder on disk."""
    datasets_config = load_datasets_config()
    dataset = next(
        (ds for ds in datasets_config.datasets if ds.id == study["dataset_id"]),
        None,
    )
    if dataset is None:
        raise ValueError(
            f"Study '{study['id']}' references dataset_id '{study['dataset_id']}' "
            f"which was not found in datasets.json"
        )
    return get_data_dir() / dataset.subfolder


def generate_study(study: dict, output_dir: Path | None = None) -> None:
    """Generate group JSON files and summary for a single study."""
    validate_study(study)

    image_folder = resolve_image_folder(study)
    if not image_folder.is_dir():
        raise ValueError(
            f"Study '{study['id']}': image folder does not exist: {image_folder}\n"
            f"Has the dataset '{study['dataset_id']}' been downloaded?"
        )

    if output_dir is None:
        output_dir = get_data_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    recursive = study.get("recursive", False)
    image_files = get_image_files(image_folder, recursive=recursive)
    if not image_files:
        raise ValueError(
            f"Study '{study['id']}': no image files found in {image_folder}"
        )

    num_groups = study["num_groups"]
    seed = study["seed"]
    share_m = study.get("share_m", 0)
    prefix = study.get("output_prefix", study["id"])
    annotator_names = study.get("annotator_names")

    rng = random.Random(seed)
    rng.shuffle(image_files)

    raw_groups = split_evenly(image_files, num_groups)
    original_groups = [
        [rel_display_path(image_folder, img) for img in group] for group in raw_groups
    ]

    final_groups, copy_info = apply_cross_group_copying(original_groups, share_m, rng)

    # Write per-group JSON files, track filenames for summary mapping
    group_filenames: list[str] = []
    for idx, group in enumerate(final_groups):
        json_data = make_json_template(group)
        if annotator_names:
            filename = f"{prefix}_{annotator_names[idx]}.json"
        else:
            filename = f"{prefix}_{idx + 1}.json"
        group_filenames.append(filename)
        output_file = output_dir / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        print(f"  Wrote {output_file} ({len(group)} images)")

    # Build summary (schema from make_image_group_data, unchanged)
    summary = build_summary(
        original_groups=original_groups,
        final_groups=final_groups,
        copy_info=copy_info,
        total_images=len(image_files),
    )

    # Prepend study context and group-to-file mapping
    group_mapping = {}
    for i in range(num_groups):
        g = f"group_{i + 1}"
        entry: dict[str, str] = {"file": group_filenames[i]}
        if annotator_names:
            entry["annotator"] = annotator_names[i]
        group_mapping[g] = entry

    summary = {
        "study_id": study["id"],
        "dataset_id": study["dataset_id"],
        "group_mapping": group_mapping,
        **summary,
    }

    summary_file = output_dir / f"{prefix}_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"  Wrote summary: {summary_file}")
    print()
    print(f"  === {study['id']} ===")
    print(f"  Total images: {len(image_files)}")
    print(f"  Groups: {num_groups}")
    print(f"  Copying enabled: {share_m > 0}")
    if share_m > 0:
        print(f"  M: {share_m}")
    for i in range(num_groups):
        g = f"group_{i + 1}"
        label = annotator_names[i] if annotator_names else g
        print(
            f"  {label} ({g}): initial={summary['initial_group_sizes'][g]}, "
            f"unique={summary['unique_counts_per_group'][g]}, "
            f"shared={summary['shared_counts_per_group'][g]}, "
            f"final={summary['final_group_sizes'][g]}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Generate annotation group files from study configurations."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--study-id",
        type=str,
        help="Generate groups for a specific study by ID",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Generate groups for all studies",
    )
    group.add_argument(
        "--list",
        action="store_true",
        help="List available studies and exit",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory (default: ~/2d-point-annotator/data/)",
    )
    parser.add_argument(
        "--studies-config",
        type=str,
        default=None,
        help="Path to studies.json (default: data/studies.json)",
    )

    args = parser.parse_args()

    config_path = Path(args.studies_config) if args.studies_config else None
    studies = load_studies_config(config_path)

    if args.list:
        print("Available studies:")
        for s in studies:
            names = s.get("annotator_names", [])
            names_str = f" [{', '.join(names)}]" if names else ""
            print(
                f"  {s['id']}: {s.get('description', '')} "
                f"({s['num_groups']} groups{names_str})"
            )
        return

    output_dir = Path(args.output_dir).resolve() if args.output_dir else None

    if args.all:
        for study in studies:
            print(f"Generating: {study['id']}")
            generate_study(study, output_dir)
            print()
    else:
        study = next((s for s in studies if s["id"] == args.study_id), None)
        if study is None:
            available = [s["id"] for s in studies]
            print(
                f"Study '{args.study_id}' not found. Available: {available}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Generating: {study['id']}")
        generate_study(study, output_dir)


if __name__ == "__main__":
    main()
