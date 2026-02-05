#!/usr/bin/env python3

import os
from pathlib import Path, PurePath
from typing import Union


def normalize_path_string(path: Union[Path, str, PurePath]) -> str:
    return str(path).replace("\\", "/")


def extract_filename(path: Union[Path, str]) -> str:
    normalized = str(path).replace("\\", os.sep)
    return PurePath(normalized).name


def filenames_match(path1: Union[Path, str], path2: Union[Path, str]) -> bool:
    return extract_filename(path1) == extract_filename(path2)


def normalize_relative_path(path: Path, base: Path) -> str:
    rel = PurePath(path.resolve()).relative_to(base.resolve(), walk_up=True)
    return normalize_path_string(rel)
