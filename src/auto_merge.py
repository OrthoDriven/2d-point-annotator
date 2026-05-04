"""
Global auto-merge for annotation JSONs.

When a user loads a JSON file, this module checks if a file with the same
name exists in the repo's data/ directory (the "source of truth"). If it
does and the image lists differ, it merges them:

  - Annotated images from the local file are ALWAYS kept
  - New images from the source are added
  - Unannotated images not in the source are dropped
  - Landmarks and views come from the source (protocol updates propagate)

This replaces the per-file json_update_rules.json system with a single
global behavior that works for any JSON by filename matching.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dirs import BASE_DIR

logger = logging.getLogger(__name__)

# Repo's source data directory
SOURCE_DATA_DIR = BASE_DIR / "data"


def _get_annotated_images(images: List[Dict[str, Any]]) -> Set[str]:
    """
    Get set of image paths that have at least one annotation.

    An image is considered "annotated" if it has:
    - Any non-empty annotations, OR
    - A view assigned, OR
    - image_flag set to True
    """
    annotated: Set[str] = set()
    for record in images:
        if not isinstance(record, dict):
            continue
        image_path = record.get("image_path")
        if not image_path:
            continue

        # Check if has annotations
        annotations = record.get("annotations", {})
        has_annotations = False
        for lm, val in annotations.items():
            if isinstance(val, dict):
                if val.get("value") is not None:
                    has_annotations = True
                    break
            elif val is not None:
                has_annotations = True
                break

        has_view = record.get("view") is not None
        has_flag = record.get("image_flag", False) is True

        if has_annotations or has_view or has_flag:
            annotated.add(image_path)

    return annotated


def _merge_image_lists(
    local_images: List[Dict[str, Any]],
    source_images: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Merge source image list into local, preserving annotations.

    Logic:
    - Keep ALL images the user has annotated (even if removed from source)
    - Add new images from source that user doesn't have
    - Remove unannotated images not in source

    Returns:
        (merged_images, stats) where stats = {kept, added, removed}
    """
    local_by_path: Dict[str, Dict[str, Any]] = {}
    for record in local_images:
        if isinstance(record, dict) and "image_path" in record:
            local_by_path[record["image_path"]] = record

    annotated_paths = _get_annotated_images(local_images)

    source_paths: Set[str] = set()
    source_by_path: Dict[str, Dict[str, Any]] = {}
    for record in source_images:
        if isinstance(record, dict) and "image_path" in record:
            path = record["image_path"]
            source_paths.add(path)
            source_by_path[path] = record

    kept = 0
    added = 0
    removed = 0

    merged: List[Dict[str, Any]] = []
    seen_paths: Set[str] = set()

    # 1. Keep all annotated images (regardless of source)
    for path, record in local_by_path.items():
        if path in annotated_paths:
            merged.append(record)
            seen_paths.add(path)
            kept += 1

    # 2. Add source images (new ones, or replace unannotated ones)
    for path, source_record in source_by_path.items():
        if path in seen_paths:
            continue

        if path in local_by_path:
            # Image exists locally but isn't annotated — use source version
            merged.append(source_record)
            seen_paths.add(path)
        else:
            # Truly new image
            merged.append(source_record)
            seen_paths.add(path)
            added += 1

    # 3. Count removed (unannotated images not in source)
    for path in local_by_path:
        if path not in seen_paths:
            removed += 1

    return merged, {"kept": kept, "added": added, "removed": removed}


def auto_merge_on_load(local_json_path: Path) -> Dict[str, Any]:
    """
    Check if a matching source JSON exists and merge if needed.

    This is the main entry point. Call it after reading a JSON file but
    before processing it in load_data().

    Parameters
    ----------
    local_json_path : Path
        Path to the user's local JSON file

    Returns
    -------
    dict
        The data to use (either the original or merged version)
    """
    filename = local_json_path.name
    source_path = SOURCE_DATA_DIR / filename

    if not source_path.exists():
        # No matching source — use local as-is
        return json.loads(local_json_path.read_text(encoding="utf-8"))

    try:
        local_data = json.loads(local_json_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read local JSON {local_json_path}: {e}")
        # Return empty structure so load_data() can show its own error
        return {"landmarks": [], "views": {}, "images": []}

    try:
        source_data = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read source JSON {source_path}: {e}")
        return local_data

    local_images = local_data.get("images", [])
    source_images = source_data.get("images", [])

    merged_images, stats = _merge_image_lists(local_images, source_images)

    # If nothing changed, check if landmarks/views differ
    if stats["added"] == 0 and stats["removed"] == 0:
        source_landmarks = source_data.get("landmarks")
        source_views = source_data.get("views")
        landmarks_differ = source_landmarks is not None and source_landmarks != local_data.get("landmarks")
        views_differ = source_views is not None and source_views != local_data.get("views")
        if not landmarks_differ and not views_differ:
            return local_data

    # Build merged result: source landmarks/views + merged images
    merged_data = dict(local_data)
    merged_data["images"] = merged_images

    # Update landmarks and views from source (protocol updates propagate)
    if "landmarks" in source_data:
        merged_data["landmarks"] = source_data["landmarks"]
    if "views" in source_data:
        merged_data["views"] = source_data["views"]

    # Update metadata
    now_iso = datetime.now().isoformat()
    metadata = merged_data.get("metadata", {})
    if "created" not in metadata:
        metadata["created"] = now_iso
    metadata["last_modified"] = now_iso
    change_log = metadata.get("change_log", [])
    change_log.append({
        "timestamp": now_iso,
        "action": "auto_merge",
        "source": filename,
        "details": (
            f"Kept {stats['kept']}, added {stats['added']}, "
            f"removed {stats['removed']} images"
        ),
    })
    metadata["change_log"] = change_log
    merged_data["metadata"] = metadata

    # Write merged result back to local file
    try:
        tmp_path = local_json_path.with_suffix(local_json_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(merged_data, indent=2), encoding="utf-8"
        )
        tmp_path.replace(local_json_path)
        logger.info(
            f"Auto-merged {filename}: "
            f"kept={stats['kept']}, added={stats['added']}, "
            f"removed={stats['removed']}"
        )
    except Exception as e:
        logger.warning(f"Failed to write merged JSON: {e}")
        # Return merged data even if write failed — in-memory is fine
        return merged_data

    return merged_data
