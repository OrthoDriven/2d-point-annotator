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


def compute_landmark_distance(val_a, val_b) -> dict | None:
    """Compute distance metrics between two landmark values.

    Point landmarks [x,y]: returns {"type": "point", "distance": float}
    Line landmarks [[x1,y1],[x2,y2]]: returns {"type": "line", "signed_dists": [float, float], "angle_deg": float}
    Returns None if either value is None.
    """
    if val_a is None or val_b is None:
        return None

    a_is_line = isinstance(val_a[0], list)
    b_is_line = isinstance(val_b[0], list)

    if not a_is_line and not b_is_line:
        return {"type": "point", "distance": math.dist(val_a, val_b)}

    if a_is_line and b_is_line:
        return _compare_lines(val_a, val_b)

    return None


def _max_metric(pairs: dict) -> float:
    vals = []
    for r in pairs.values():
        if r["type"] == "point":
            vals.append(r["distance"])
        elif r["type"] == "line":
            vals.append(max(abs(d) for d in r["signed_dists"]))
    return max(vals) if vals else 0.0


def _compare_lines(line_a: list, line_b: list) -> dict:
    """Compare two line landmarks: signed perpendicular distances + angle."""
    ax1, ay1 = line_a[0]
    ax2, ay2 = line_a[1]
    bx1, by1 = line_b[0]
    bx2, by2 = line_b[1]

    # Direction vector of line B
    bdx, bdy = bx2 - bx1, by2 - by1
    blen = math.hypot(bdx, bdy)
    if blen < 1e-9:
        return {"type": "line", "signed_dists": [0.0, 0.0], "angle_deg": 0.0}

    # Unit normal of line B (perpendicular, pointing "left" relative to direction)
    nx, ny = -bdy / blen, bdx / blen

    # Signed distance from each endpoint of A to line B's infinite line
    d1 = (ax1 - bx1) * nx + (ay1 - by1) * ny
    d2 = (ax2 - bx1) * nx + (ay2 - by1) * ny

    # Angle between the two lines
    adx, ady = ax2 - ax1, ay2 - ay1
    alen = math.hypot(adx, ady)
    if alen < 1e-9:
        return {"type": "line", "signed_dists": [d1, d2], "angle_deg": 0.0}

    dot = (adx * bdx + ady * bdy) / (alen * blen)
    dot = max(-1.0, min(1.0, dot))  # clamp for float precision
    angle_rad = math.acos(dot)
    angle_deg = math.degrees(angle_rad)

    return {"type": "line", "signed_dists": [d1, d2], "angle_deg": angle_deg}


def compute_pairwise_distances(
    annotators: dict[str, dict], image_path: str, landmarks: list[str]
) -> dict[str, dict[tuple[str, str], dict | None]]:
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
            point_dists = []
            line_angles = []
            line_max_signed = []
            for pairs in distances.values():
                for result in pairs.values():
                    if result["type"] == "point":
                        point_dists.append(result["distance"])
                    elif result["type"] == "line":
                        line_angles.append(result["angle_deg"])
                        line_max_signed.append(max(abs(d) for d in result["signed_dists"]))

            if point_dists:
                print(f"  Point distances: min={min(point_dists):.1f}px, max={max(point_dists):.1f}px, mean={sum(point_dists)/len(point_dists):.1f}px")
            if line_angles:
                print(f"  Line angles: min={min(line_angles):.1f}°, max={max(line_angles):.1f}°, mean={sum(line_angles)/len(line_angles):.1f}°")
            if line_max_signed:
                print(f"  Line offsets: min={min(line_max_signed):.1f}px, max={max(line_max_signed):.1f}px, mean={sum(line_max_signed)/len(line_max_signed):.1f}px")

            worst = sorted(
                [(lm, _max_metric(pairs)) for lm, pairs in distances.items() if pairs],
                key=lambda x: x[1], reverse=True
            )[:3]
            if worst:
                print(f"  Worst landmarks:")
                for lm, d in worst:
                    print(f"    {lm}: {d:.1f}")

    print(f"\n{'='*60}")
    print("Data layer verification complete.")
