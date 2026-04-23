import json
import math
import itertools
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from PIL import Image, ImageTk


def load_summary(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def discover_annotator_files(summary: dict, data_dir: Path) -> dict[str, Path]:
    result = {}
    group_mapping = summary.get("group_mapping", {})
    for group_id, info in group_mapping.items():
        annotator = info["annotator"]
        file_path = data_dir / info["file"]
        if file_path.exists():
            result[annotator] = file_path
    return result


def get_shared_images(summary: dict) -> list[str]:
    membership = summary["rounds"][0]["image_membership"]
    return sorted(img for img, groups in membership.items() if len(groups) >= 2)


def load_annotator_data(path: Path) -> dict:
    """Load an annotator's JSON file."""
    with open(path) as f:
        return json.load(f)


def get_annotations_for_image(annotator_data: dict, image_path: str) -> dict:
    """Return annotations dict for a specific image, or empty dict if not found."""
    for img in annotator_data.get("images", []):
        if img["image_path"] == image_path:
            return img.get("annotations", {})
    return {}


def compute_landmark_distance(val_a, val_b) -> float | None:
    """Compute pixel distance between two landmark values.

    Handles point landmarks [x,y] and line landmarks [[x1,y1],[x2,y2]].
    Returns None if either value is None.
    """
    if val_a is None or val_b is None:
        return None

    def midpoint(val):
        if isinstance(val[0], list):
            return [(val[0][0] + val[1][0]) / 2, (val[0][1] + val[1][1]) / 2]
        return val

    return math.dist(midpoint(val_a), midpoint(val_b))


def compute_pairwise_distances(
    annotators: dict[str, dict], image_path: str, landmarks: list[str]
) -> dict[str, dict[tuple[str, str], float]]:
    """Compute pairwise pixel distances for all landmarks across annotators.

    Returns {landmark: {(ann_a, ann_b): distance}}
    """
    result = {}
    for lm in landmarks:
        values = {}
        for name, data in annotators.items():
            anns = get_annotations_for_image(data, image_path)
            if lm in anns:
                values[name] = anns[lm]["value"]

        pairs = {}
        for a, b in itertools.combinations(sorted(values.keys()), 2):
            dist = compute_landmark_distance(values[a], values[b])
            if dist is not None:
                pairs[(a, b)] = dist
        result[lm] = pairs
    return result


def detect_mismatches(
    annotators: dict[str, dict], image_path: str, landmarks: list[str]
) -> dict[str, str]:
    """Detect mismatches across annotators for each landmark.

    Returns {landmark: 'ok' | 'missing' | 'flagged'}
    Priority: missing > flagged > ok
    """
    result = {}
    for lm in landmarks:
        has_null = False
        has_flagged = False
        for name, data in annotators.items():
            anns = get_annotations_for_image(data, image_path)
            if lm not in anns:
                continue
            ann = anns[lm]
            if ann["value"] is None:
                has_null = True
            if ann.get("flag", False):
                has_flagged = True
        result[lm] = "missing" if has_null else ("flagged" if has_flagged else "ok")
    return result


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Inter-Annotator QC Viewer — data verification")
    parser.add_argument("--summary", required=True, help="Path to summary JSON")
    parser.add_argument("--json-dir", required=True, help="Directory containing annotator JSONs")
    parser.add_argument("--images-dir", default=None, help="Directory containing images (optional, for existence check)")
    parser.add_argument("--max-images", type=int, default=5, help="Max shared images to report on (default 5)")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    json_dir = Path(args.json_dir)
    images_dir = Path(args.images_dir) if args.images_dir else None

    print(f"Loading summary: {summary_path}")
    summary = load_summary(summary_path)

    print(f"Discovering annotators in: {json_dir}")
    annotator_files = discover_annotator_files(summary, json_dir)
    print(f"Found {len(annotator_files)} annotators: {sorted(annotator_files.keys())}")

    annotators = {}
    for name, path in annotator_files.items():
        annotators[name] = load_annotator_data(path)
        n_images = len(annotators[name].get("images", []))
        print(f"  {name}: {n_images} images")

    shared_images = get_shared_images(summary)
    print(f"\nShared images: {len(shared_images)}")

    landmarks = next(iter(annotators.values()), {}).get("landmarks", [])
    print(f"Landmarks: {len(landmarks)}")

    print(f"\n{'='*60}")
    print(f"Inspecting first {min(args.max_images, len(shared_images))} shared images:")
    print(f"{'='*60}")

    for image_path in shared_images[:args.max_images]:
        print(f"\n--- {image_path} ---")

        if images_dir:
            full_path = images_dir / image_path
            print(f"  Image exists: {full_path.exists()}")

        mismatches = detect_mismatches(annotators, image_path, landmarks)
        distances = compute_pairwise_distances(annotators, image_path, landmarks)

        missing = [lm for lm, s in mismatches.items() if s == "missing"]
        flagged = [lm for lm, s in mismatches.items() if s == "flagged"]
        ok = [lm for lm, s in mismatches.items() if s == "ok"]

        print(f"  Status: {len(ok)} ok, {len(flagged)} flagged, {len(missing)} missing")

        if missing:
            print(f"  Missing: {', '.join(missing)}")
        if flagged:
            print(f"  Flagged: {', '.join(flagged)}")

        if distances:
            all_dists = [d for pairs in distances.values() for d in pairs.values()]
            if all_dists:
                print(f"  Distances: min={min(all_dists):.1f}px, max={max(all_dists):.1f}px, mean={sum(all_dists)/len(all_dists):.1f}px")

                worst = sorted(
                    [(lm, max(pairs.values())) for lm, pairs in distances.items() if pairs],
                    key=lambda x: x[1], reverse=True
                )[:3]
                if worst:
                    print(f"  Worst landmarks:")
                    for lm, d in worst:
                        print(f"    {lm}: {d:.1f}px")

    print(f"\n{'='*60}")
    print("Data layer verification complete.")
