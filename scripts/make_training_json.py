#!/usr/bin/env python3
"""
Generate a training JSON from a folder of images.

Usage:
    python scripts/make_training_json.py <image_folder> [output_name]

Example:
    python scripts/make_training_json.py ~/images/fluoro training_set.json
"""

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
DATA_DIR = REPO_ROOT / "data"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

LANDMARKS = [
    "L-LIP", "R-LIP", "L-POD", "R-POD", "L-PT", "R-PT",
    "L-IT", "R-IT", "L-SPS", "R-SPS", "L-IPS", "R-IPS",
    "L-DSI", "R-DSI", "L-AC", "R-AC", "L-SAB", "R-SAB",
    "L-DAB", "R-DAB", "L-FHC", "R-FHC", "L-SGT", "R-SGT",
    "L-LGT", "R-LGT", "L-PLT", "R-PLT", "L-MLT", "R-MLT",
    "L-DLT", "R-DLT", "L-FA", "R-FA",
]

VIEWS = {
    "AP Bilateral": LANDMARKS[:],
    "AP Unilateral (Left)": [l for l in LANDMARKS if l.startswith("L-")],
    "AP Unilateral (Right)": [l for l in LANDMARKS if l.startswith("R-")],
}


def get_image_files(folder: Path):
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def main():
    parser = argparse.ArgumentParser(description="Generate a training JSON from a folder of images.")
    parser.add_argument("image_folder", type=str, help="Folder containing images")
    parser.add_argument("-o", "--output", type=str, default="training_set.json", help="Output filename (default: training_set.json)")
    parser.add_argument("-n", "--num", type=int, default=None, help="Number of images to include (default: all)")
    parser.add_argument("--shuffle", action="store_true", help="Randomly shuffle image order")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible shuffle")

    args = parser.parse_args()
    image_folder = Path(args.image_folder).resolve()

    if not image_folder.is_dir():
        print(f"Not a directory: {image_folder}")
        sys.exit(1)

    image_files = get_image_files(image_folder)
    if not image_files:
        print(f"No images found in {image_folder}")
        sys.exit(1)

    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(image_files)

    if args.num:
        image_files = image_files[:args.num]

    images = [
        {
            "image_path": f"{image_folder.name}/{img.name}",
            "image_flag": False,
            "view": None,
            "annotations": {},
        }
        for img in image_files
    ]

    data = {
        "landmarks": LANDMARKS,
        "views": VIEWS,
        "images": images,
    }

    out_path = DATA_DIR / args.output
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(images)} images to {out_path}")


if __name__ == "__main__":
    main()
