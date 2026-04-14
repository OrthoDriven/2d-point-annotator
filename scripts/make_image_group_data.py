#!/usr/bin/env python3

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

LANDMARKS = [
    "L-LIP",
    "R-LIP",
    "L-POD",
    "R-POD",
    "L-PT",
    "R-PT",
    "L-IT",
    "R-IT",
    "L-SPS",
    "R-SPS",
    "L-IPS",
    "R-IPS",
    "L-DSI",
    "R-DSI",
    "L-AC",
    "R-AC",
    "L-SAB",
    "R-SAB",
    "L-DAB",
    "R-DAB",
    "L-FHC",
    "R-FHC",
    "L-SGT",
    "R-SGT",
    "L-LGT",
    "R-LGT",
    "L-PLT",
    "R-PLT",
    "L-MLT",
    "R-MLT",
    "L-DLT",
    "R-DLT",
    "L-FA",
    "R-FA",
]

VIEWS = {
    "AP Bilateral": [
        "L-LIP",
        "R-LIP",
        "L-POD",
        "R-POD",
        "L-PT",
        "R-PT",
        "L-IT",
        "R-IT",
        "L-SPS",
        "R-SPS",
        "L-IPS",
        "R-IPS",
        "L-DSI",
        "R-DSI",
        "L-AC",
        "R-AC",
        "L-SAB",
        "R-SAB",
        "L-DAB",
        "R-DAB",
        "L-FHC",
        "R-FHC",
        "L-SGT",
        "R-SGT",
        "L-LGT",
        "R-LGT",
        "L-PLT",
        "R-PLT",
        "L-MLT",
        "R-MLT",
        "L-DLT",
        "R-DLT",
        "L-FA",
        "R-FA",
    ],
    "AP Unilateral (Left)": [
        "L-LIP",
        "L-POD",
        "L-PT",
        "L-IT",
        "L-SPS",
        "L-IPS",
        "L-DSI",
        "L-AC",
        "L-SAB",
        "L-DAB",
        "L-FHC",
        "L-SGT",
        "L-LGT",
        "L-PLT",
        "L-MLT",
        "L-DLT",
        "L-FA",
    ],
    "AP Unilateral (Right)": [
        "R-LIP",
        "R-POD",
        "R-PT",
        "R-IT",
        "R-SPS",
        "R-IPS",
        "R-DSI",
        "R-AC",
        "R-SAB",
        "R-DAB",
        "R-FHC",
        "R-SGT",
        "R-LGT",
        "R-PLT",
        "R-MLT",
        "R-DLT",
        "R-FA",
    ],
}


def get_image_files(folder: Path, recursive: bool = False):
    image_extensions = {
        ".tif",
        ".tiff",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".webp",
    }

    if recursive:
        files = [
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in image_extensions
        ]
    else:
        files = [
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in image_extensions
        ]

    return sorted(files)


def split_evenly(items, n_groups):
    total = len(items)
    base_size = total // n_groups
    remainder = total % n_groups

    groups = []
    start = 0
    for i in range(n_groups):
        group_size = base_size + (1 if i < remainder else 0)
        groups.append(items[start : start + group_size])
        start += group_size

    return groups


def make_json_template(image_paths):
    return {
        "landmarks": LANDMARKS,
        "views": VIEWS,
        "images": [
            {
                "image_path": image_path,
                "image_flag": False,
                "view": None,
                "annotations": {},
            }
            for image_path in image_paths
        ],
    }


def rel_display_path(input_folder: Path, image_path: Path):
    return f"{input_folder.name}/{image_path.name}"


def apply_cross_group_copying(groups, m, rng):
    """
    groups: list[list[str]]
    Behavior:
      - sample M images from each group
      - keep them in their original group
      - copy them to every other group
      - re-randomize each final group
    """
    n = len(groups)

    if m is None or m == 0:
        image_membership = {}
        for i, group in enumerate(groups):
            for img in group:
                image_membership[img] = [f"group_{i + 1}"]

        return groups, {
            "copying_enabled": False,
            "m": 0,
            "sampled_by_group": {},
            "copied_into_group": {f"group_{i + 1}": [] for i in range(n)},
            "unique_by_group": {f"group_{i + 1}": sorted(groups[i]) for i in range(n)},
            "shared_by_group": {f"group_{i + 1}": [] for i in range(n)},
            "image_membership": image_membership,
        }

    for i, group in enumerate(groups):
        if m > len(group):
            raise ValueError(
                f"--share-m={m} is too large for group_{i + 1}, which has only {len(group)} images."
            )

    original_groups = [list(group) for group in groups]
    sampled_by_group = []

    for group in original_groups:
        sampled = rng.sample(group, m)
        sampled_by_group.append(sampled)

    final_groups = [list(group) for group in original_groups]
    copied_into_group = defaultdict(list)

    for source_idx in range(n):
        sampled_images = sampled_by_group[source_idx]
        for target_idx in range(n):
            if source_idx == target_idx:
                continue
            final_groups[target_idx].extend(sampled_images)
            copied_into_group[f"group_{target_idx + 1}"].extend(sampled_images)

    for i in range(n):
        rng.shuffle(final_groups[i])

    image_membership = defaultdict(list)
    for i, group in enumerate(final_groups):
        group_name = f"group_{i + 1}"
        for img in group:
            image_membership[img].append(group_name)

    unique_by_group = {}
    shared_by_group = {}

    for i, original_group in enumerate(original_groups):
        group_name = f"group_{i + 1}"
        unique_imgs = []
        shared_imgs = []

        for img in final_groups[i]:
            memberships = image_membership[img]
            if len(memberships) == 1:
                unique_imgs.append(img)
            else:
                shared_imgs.append(img)

        unique_by_group[group_name] = sorted(set(unique_imgs))
        shared_by_group[group_name] = sorted(set(shared_imgs))

    info = {
        "copying_enabled": True,
        "m": m,
        "sampled_by_group": {
            f"group_{i + 1}": sorted(sampled_by_group[i]) for i in range(n)
        },
        "copied_into_group": {
            f"group_{i + 1}": sorted(copied_into_group[f"group_{i + 1}"])
            for i in range(n)
        },
        "unique_by_group": unique_by_group,
        "shared_by_group": shared_by_group,
        "image_membership": {
            img: sorted(group_list)
            for img, group_list in sorted(image_membership.items())
        },
    }

    return final_groups, info


def build_summary(original_groups, final_groups, copy_info, total_images):
    n = len(original_groups)

    initial_sizes = {f"group_{i + 1}": len(original_groups[i]) for i in range(n)}
    final_sizes = {f"group_{i + 1}": len(final_groups[i]) for i in range(n)}
    unique_counts = {g: len(v) for g, v in copy_info["unique_by_group"].items()}
    shared_counts = {g: len(v) for g, v in copy_info["shared_by_group"].items()}

    per_group_accounting = {}
    for i in range(n):
        g = f"group_{i + 1}"
        per_group_accounting[g] = {
            "initial_size": initial_sizes[g],
            "unique_count": unique_counts[g],
            "shared_count": shared_counts[g],
            "final_size": final_sizes[g],
            "check_unique_plus_shared_equals_final": unique_counts[g] + shared_counts[g]
            == final_sizes[g],
        }

    membership_histogram = defaultdict(int)
    for img, memberships in copy_info["image_membership"].items():
        membership_histogram[len(memberships)] += 1

    sum_initial = sum(initial_sizes.values())
    sum_final = sum(final_sizes.values())
    sum_unique = sum(unique_counts.values())
    total_shared_assignments = 0

    for img, memberships in copy_info["image_membership"].items():
        if len(memberships) > 1:
            total_shared_assignments += len(memberships)

    notes = [
        "Initial grouping partitions the original image set exactly once.",
        "If copying is enabled, sampled images remain in their source group and are also copied to every other group.",
        "For group i: final_size_i = initial_size_i + (N-1)*M, assuming M sampled from every group.",
        "For group i: unique_count_i = initial_size_i - M.",
        "For group i: shared_count_i = N*M.",
        "A sampled image from one group appears in all N groups after copying.",
        "A non-sampled image appears in exactly 1 group.",
    ]

    global_accounting = {
        "total_original_images": total_images,
        "sum_initial_group_sizes": sum_initial,
        "sum_final_group_sizes": sum_final,
        "sum_unique_counts": sum_unique,
        "total_shared_assignments": total_shared_assignments,
        "initial_sizes_match_total_images": sum_initial == total_images,
        "final_sizes_match_unique_plus_shared": sum_final
        == (sum_unique + total_shared_assignments),
    }

    if copy_info["copying_enabled"]:
        expected_sum_unique = sum(
            initial_sizes[g] - copy_info["m"] for g in initial_sizes
        )
        expected_sum_final = sum(
            initial_sizes[g] + (n - 1) * copy_info["m"] for g in initial_sizes
        )
        global_accounting["expected_sum_unique"] = expected_sum_unique
        global_accounting["expected_sum_final"] = expected_sum_final
        global_accounting["unique_counts_match_expected"] = (
            sum_unique == expected_sum_unique
        )
        global_accounting["final_sizes_match_expected"] = (
            sum_final == expected_sum_final
        )
    else:
        global_accounting["expected_sum_unique"] = total_images
        global_accounting["expected_sum_final"] = total_images
        global_accounting["unique_counts_match_expected"] = sum_unique == total_images
        global_accounting["final_sizes_match_expected"] = sum_final == total_images

    return {
        "total_original_images": total_images,
        "num_groups": n,
        "copying_enabled": copy_info["copying_enabled"],
        "share_m": copy_info["m"],
        "initial_group_sizes": initial_sizes,
        "final_group_sizes": final_sizes,
        "unique_counts_per_group": unique_counts,
        "shared_counts_per_group": shared_counts,
        "sampled_by_group": copy_info["sampled_by_group"],
        "copied_into_group": copy_info["copied_into_group"],
        "unique_by_group": copy_info["unique_by_group"],
        "shared_by_group": copy_info["shared_by_group"],
        "image_membership": copy_info["image_membership"],
        "membership_histogram": dict(sorted(membership_histogram.items())),
        "per_group_accounting": per_group_accounting,
        "global_accounting": global_accounting,
        "notes": notes,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Randomize images, split into N groups, optionally sample M images from each group "
            "and copy those sampled images to every other group, then write JSON files."
        )
    )
    parser.add_argument("input_folder", type=str, help="Folder containing images")
    parser.add_argument(
        "num_groups", type=int, help="Number of groups / JSON files to create"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save JSON files (default: input folder)",
    )
    parser.add_argument(
        "--seed", type=int, default=1234, help="Random seed for reproducible shuffling"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search for images recursively in subfolders",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="group",
        help="Prefix for output JSON filenames (default: group)",
    )
    parser.add_argument(
        "--share-m",
        type=int,
        default=0,
        help=(
            "After initial grouping, sample M images from each group and copy those sampled "
            "images to every other group while retaining them in the source group."
        ),
    )

    args = parser.parse_args()

    input_folder = Path(args.input_folder).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_folder

    if not input_folder.is_dir():
        raise ValueError(
            f"Input folder does not exist or is not a directory: {input_folder}"
        )

    if args.num_groups <= 0:
        raise ValueError("num_groups must be > 0")

    if args.share_m < 0:
        raise ValueError("--share-m must be >= 0")

    if args.share_m > 0 and args.num_groups < 2:
        raise ValueError("--share-m requires at least 2 groups.")

    output_dir.mkdir(parents=True, exist_ok=True)

    image_files = get_image_files(input_folder, recursive=args.recursive)
    if not image_files:
        raise ValueError(f"No image files found in: {input_folder}")

    rng = random.Random(args.seed)
    rng.shuffle(image_files)

    raw_groups = split_evenly(image_files, args.num_groups)
    original_groups = [
        [rel_display_path(input_folder, img) for img in group] for group in raw_groups
    ]

    final_groups, copy_info = apply_cross_group_copying(
        original_groups, args.share_m, rng
    )

    for idx, group in enumerate(final_groups, start=1):
        json_data = make_json_template(group)
        output_file = output_dir / f"{args.prefix}_{idx}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        print(f"Wrote {output_file} with {len(group)} images")

    summary = build_summary(
        original_groups=original_groups,
        final_groups=final_groups,
        copy_info=copy_info,
        total_images=len(image_files),
    )

    summary_file = output_dir / f"{args.prefix}_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote summary: {summary_file}")
    print()
    print("=== Summary ===")
    print(f"Total original images: {len(image_files)}")
    print(f"Groups: {args.num_groups}")
    print(f"Copying enabled: {args.share_m > 0}")
    if args.share_m > 0:
        print(f"M: {args.share_m}")
    for i in range(args.num_groups):
        g = f"group_{i + 1}"
        print(
            f"{g}: initial={summary['initial_group_sizes'][g]}, "
            f"unique={summary['unique_counts_per_group'][g]}, "
            f"shared={summary['shared_counts_per_group'][g]}, "
            f"final={summary['final_group_sizes'][g]}"
        )


if __name__ == "__main__":
    main()
