#!/usr/bin/env python3
"""
Inject new images into an existing annotation JSON file.

Usage:
    python inject_images.py <json_path> <image_dir_or_files...>

Examples:
    # Add all images from a directory
    python inject_images.py data/fluoro-r2_round2_andrew.json /path/to/new_images/

    # Add specific files
    python inject_images.py data/fluoro-r2_round2_andrew.json img1.tif img2.tif img3.tif

    # Add images and also backup original to OneDrive
    python inject_images.py --backup data/fluoro-r2_round2_andrew.json /path/to/new_images/

The script:
- Reads the existing JSON
- Adds new images (deduplicates by image_path)
- Preserves all existing annotations, views, flags, and notes
- Updates metadata with change_log entry
- Writes back atomically (tmp + replace)
- Optionally backs up original to OneDrive (--backup flag)
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Supported image extensions
IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
}


def find_images_in_dir(dir_path: Path) -> List[Path]:
    """Recursively find all image files in a directory."""
    images = []
    for f in sorted(dir_path.rglob("*")):
        if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES:
            images.append(f)
    return images


def resolve_image_path(image_path: Path, json_dir: Path) -> str:
    """
    Resolve image path relative to the JSON directory.
    Returns a relative path string suitable for the JSON.
    """
    try:
        return str(image_path.resolve().relative_to(json_dir.resolve()))
    except ValueError:
        # If not relative, use absolute path
        return str(image_path.resolve())


def inject_images(
    json_path: Path,
    new_image_paths: List[Path],
    backup_to_onedrive: bool = False,
) -> Dict:
    """
    Inject new images into an existing annotation JSON.

    Parameters
    ----------
    json_path : Path
        Path to the existing JSON file
    new_image_paths : list of Path
        Image files to add (deduplicated by resolved path)
    backup_to_onedrive : bool
        If True, upload original JSON to OneDrive before overwriting

    Returns
    -------
    dict with stats: {added, skipped, total_before, total_after}
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON not found: {json_path}")

    # Load existing JSON
    with json_path.open("r", encoding="utf-8") as f:
        raw_content = f.read()
        data = json.loads(raw_content)

    original_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    json_dir = json_path.parent

    # Build set of existing image paths for dedup
    existing_paths: Set[str] = set()
    for record in data.get("images", []):
        if isinstance(record, dict) and "image_path" in record:
            existing_paths.add(record["image_path"])

    # Find and add new images
    added = 0
    skipped = 0
    images_list = data.setdefault("images", [])

    for img_path in new_image_paths:
        if not img_path.exists():
            print(f"  Warning: {img_path} does not exist, skipping")
            skipped += 1
            continue

        rel_path = resolve_image_path(img_path, json_dir)

        if rel_path in existing_paths:
            skipped += 1
            continue

        # Add new image record
        images_list.append(
            {
                "image_path": rel_path,
                "image_flag": False,
                "view": None,
                "annotations": {},
            }
        )
        existing_paths.add(rel_path)
        added += 1

    # Update metadata
    now_iso = datetime.now().isoformat()
    metadata = data.get("metadata", {})
    if "created" not in metadata:
        metadata["created"] = now_iso
    metadata["last_modified"] = now_iso

    change_log = metadata.get("change_log", [])
    if added > 0:
        change_log.append(
            {
                "timestamp": now_iso,
                "action": "images_added",
                "details": f"Added {added} image(s) via inject_images.py",
            }
        )
    metadata["change_log"] = change_log
    data["metadata"] = metadata

    # Backup original to OneDrive if requested
    if backup_to_onedrive and added > 0:
        try:
            _backup_to_onedrive(json_path, original_hash)
        except Exception as e:
            print(f"  Warning: OneDrive backup failed: {e}")

    # Write back atomically
    if added > 0:
        tmp_path = json_path.with_suffix(json_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp_path.replace(json_path)
        print(f"  Wrote {json_path.name} with {added} new image(s)")
    else:
        print(f"  No new images to add")

    return {
        "added": added,
        "skipped": skipped,
        "total_before": len(existing_paths) - added,
        "total_after": len(existing_paths),
    }


def _backup_to_onedrive(json_path: Path, original_hash: str) -> None:
    """Backup original JSON to OneDrive."""
    import getpass
    import threading

    try:
        from auth import SHAREPOINT_DRIVE_ID, OneDriveBackup
    except ImportError:
        print("  Warning: Cannot import auth module, skipping OneDrive backup")
        return

    try:
        username = getpass.getuser()
    except (KeyError, OSError):
        import os

        username = os.getenv("USER") or os.getenv("USERNAME") or "default_user"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{json_path.stem}_{timestamp}{json_path.suffix}"

    with json_path.open("rb") as f:
        file_content = f.read()

    def _do_upload():
        try:
            backup = OneDriveBackup()
            client = backup._create_fresh_client()
            if not client:
                print("  Warning: No Graph client available for backup")
                return

            import asyncio

            loop = asyncio.SelectorEventLoop()

            async def upload():
                remote_folder = f"pelvic-2d-points-backup/original_jsons/{username}"
                drive_item_path = f"root:/{remote_folder}/{backup_name}:"
                await (
                    client.drives.by_drive_id(SHAREPOINT_DRIVE_ID)
                    .items.by_drive_item_id(drive_item_path)
                    .content.put(file_content)
                )
                print(f"  Backed up original to OneDrive: {backup_name}")

            try:
                loop.run_until_complete(upload())
            finally:
                loop.close()
        except Exception as e:
            print(f"  Warning: OneDrive upload failed: {e}")

    # Run in background thread so we don't block
    thread = threading.Thread(target=_do_upload, daemon=True)
    thread.start()

    thread.join(timeout=10.0)  # Wait up to 10 seconds


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]
    backup_flag = False

    if args[0] == "--backup":
        backup_flag = True
        args = args[1:]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    json_path = Path(args[0])
    if not json_path.exists():
        print(f"Error: JSON not found: {json_path}")
        sys.exit(1)

    # Collect image paths from arguments
    image_paths: List[Path] = []
    for arg in args[1:]:
        p = Path(arg)
        if p.is_dir():
            image_paths.extend(find_images_in_dir(p))
        elif p.is_file():
            image_paths.append(p)
        else:
            print(f"  Warning: {arg} not found, skipping")

    if not image_paths:
        print("No images to inject")
        sys.exit(0)

    print(f"Injecting images into {json_path.name}...")
    print(f"  Found {len(image_paths)} image(s) to process")

    stats = inject_images(json_path, image_paths, backup_to_onedrive=backup_flag)

    print(f"\nDone:")
    print(f"  Added: {stats['added']}")
    print(f"  Skipped (already exists): {stats['skipped']}")
    print(f"  Total images: {stats['total_after']}")


if __name__ == "__main__":
    main()
