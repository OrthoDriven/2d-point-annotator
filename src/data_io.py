"""Data I/O utilities — JSON parsing, SQLite operations. No Tk dependency."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Union

logger = logging.getLogger(__name__)

AnnotationPoint = Tuple[float, float]
AnnotationValue = Union[AnnotationPoint, List[AnnotationPoint]]


def parse_annotations_for_record(
    record: dict[str, object],
    landmarks: list[str],
    line_landmarks: set[str],
) -> tuple[
    dict[str, AnnotationValue],
    dict[str, dict[str, object]],
    dict[str, dict[str, bool | str]],
]:
    """Parse JSON record annotations into point/line values and per-image state."""
    pts: Dict[str, AnnotationValue] = {}
    annotations_obj = record.get("annotations", {})
    annotations = annotations_obj if isinstance(annotations_obj, dict) else {}
    per_img_settings: Dict[str, Dict[str, object]] = {}
    per_img_meta: Dict[str, Dict[str, Union[bool, str]]] = {}

    for lm in landmarks:
        raw = annotations.get(lm)
        if raw is None:
            continue

        if isinstance(raw, dict):
            val = raw.get("value")
            per_img_meta[lm] = {
                "flag": bool(raw.get("flag", False)),
                "note": str(raw.get("note", "")),
            }
        else:
            val = raw
            per_img_meta[lm] = {"flag": False, "note": ""}

        if val is None:
            continue

        if lm in line_landmarks:
            if isinstance(val, list):
                line_pts: List[Tuple[float, float]] = []
                for point in val:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        try:
                            line_pts.append((float(point[0]), float(point[1])))
                        except (TypeError, ValueError):
                            continue
                if line_pts:
                    pts[lm] = line_pts[:2]
            continue

        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                pts[lm] = (float(val[0]), float(val[1]))
            except (TypeError, ValueError):
                continue

            if lm in ("LOB", "ROB") and len(val) >= 8:
                method_code = str(val[2])
                per_img_settings[lm] = {
                    "method": "Flood Fill"
                    if method_code in ("FF", "Flood Fill")
                    else "Adaptive CC",
                    "sens": int(val[3]),
                    "edge_lock": int(val[4]),
                    "edge_width": int(val[5]),
                    "clahe": int(val[6]),
                    "grow": int(val[7]),
                }

    return pts, per_img_settings, per_img_meta


def init_database(db_path: Path) -> None:
    """Create/migrate SQLite annotations table."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
                    CREATE TABLE IF NOT EXISTS annotations (
                    image_filename TEXT PRIMARY KEY,
                    image_path TEXT,
                    image_quality INTEGER DEFAULT 0,
                    data BLOB, -- JSON blob of all landmarks
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified INTEGER DEFAULT 0
                )
                """
        )
        conn.execute(
            """
                CREATE INDEX IF NOT EXISTS image_filename
                ON annotations(image_filename DESC)
                """
        )
        cols = [
            elem[1]
            for elem in conn.execute(
                """
                PRAGMA table_info(annotations)
                """
            )
        ]

        if "verified" not in cols:
            conn.execute(
                """
                    ALTER TABLE annotations ADD COLUMN verified INTEGER DEFAULT 0
                    """
            )
        conn.commit()


def db_is_populated(db_path: Path) -> bool:
    """Check whether SQLite annotations table contains rows."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM annotations")
            count = cursor.fetchone()[0]
        return count > 0
    except sqlite3.Error:
        return False
