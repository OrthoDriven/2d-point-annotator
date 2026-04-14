"""Image navigation utilities — directory scanning, path detection. No Tk dependency."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]


class _HasColumns(Protocol):
    columns: Sequence[str]


def get_image_index_from_directory(
    image_path: str | Path | None,
    possible_suffixes: set[str],
) -> tuple[int, list[str]]:
    """Find current image index in its directory's sorted image list.

    Extracted from AnnotationGUI._get_image_index_from_directory.
    Takes image_path and suffixes as params instead of reading self.*.
    Returns (index, sorted_filenames).
    """
    if image_path is None:
        return 0, []
    current_image_directory = Path(image_path).resolve().parent
    current_image_name = extract_filename(image_path)

    all_files = [
        file.name
        for file in current_image_directory.iterdir()
        if file.suffix.lower() in possible_suffixes
    ]

    all_files.sort()

    try:
        idx = all_files.index(current_image_name)
    except ValueError:
        current_lower = current_image_name.lower()
        for i, fname in enumerate(all_files):
            if fname.lower() == current_lower:
                idx = i
                break
        else:
            raise ValueError(
                f"Current image '{current_image_name}' not found in directory. Available files: {all_files[:5]}..."
            )

    return idx, all_files


def detect_path_column(df: _HasColumns, candidates: list[str] | None = None) -> str:
    """Detect which DataFrame column contains file paths."""
    candidates = candidates or [
        "image_path",
        "Dataset",
        "dataset",
        "path",
        "file",
        "filename",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    if len(df.columns) > 0:
        return df.columns[0]

    return "image_path"
