#!/usr/bin/env python3
"""CLI smoke test for dataset downloads.

Run with:
    pixi run python scripts/test_download.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dataset_config import get_dataset_dest, load_datasets_config
from downloader import download_dataset


def _prompt_choice(prompt: str, default_index: int, max_index: int) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default_index
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= value <= max_index:
            return value - 1
        print(f"Please choose a number from 1 to {max_index}.")


def _prompt_method(default_method: str) -> str:
    raw = (
        input(f"Method override [zip/graph] (Enter for default '{default_method}'): ")
        .strip()
        .lower()
    )
    if not raw:
        return default_method
    if raw in {"zip", "graph"}:
        return raw
    print("Unknown method; using default.")
    return default_method


def _list_downloaded_files(dest: Path) -> None:
    if not dest.exists():
        print(f"Destination does not exist yet: {dest}")
        return
    print(f"Downloaded files in {dest}:")
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            print(f"- {path.relative_to(dest)}")


def main() -> int:
    try:
        config = load_datasets_config()
        datasets = config.datasets
        if not datasets:
            print("No datasets found in data/datasets.json")
            return 1

        print("Available datasets:")
        for idx, dataset in enumerate(datasets, start=1):
            desc = f" — {dataset.description}" if dataset.description else ""
            print(f"{idx}. {dataset.name} ({dataset.id}){desc}")

        dataset_index = 0
        if len(datasets) > 1:
            dataset_index = _prompt_choice(
                f"Pick a dataset [1-{len(datasets)}] (Enter for 1): ", 0, len(datasets)
            )
        dataset = datasets[dataset_index]

        default_method = config.download_method or "zip"
        method = _prompt_method(default_method)

        dest = get_dataset_dest(dataset)

        if dest.exists() and any(dest.iterdir()):
            n_files = sum(1 for _ in dest.rglob("*") if _.is_file())
            print(f"Dataset already exists at {dest} ({n_files} files).")
            ans = (
                input("Download again? Existing files will be overwritten. [y/N] ")
                .strip()
                .lower()
            )
            if ans != "y":
                print("Skipped.")
                return 0

        print(f"Downloading '{dataset.name}' to {dest}")

        done_error: dict[str, Optional[Exception]] = {"error": None}

        def on_progress(message: str) -> None:
            print(message)

        def on_done(exc: Optional[Exception]) -> None:
            done_error["error"] = exc

        thread = download_dataset(
            dataset, method, on_progress=on_progress, on_done=on_done
        )
        thread.join()

        if done_error["error"] is not None:
            print(f"Download failed: {done_error['error']}")
            return 1

        print(f"Download finished: {dest}")
        _list_downloaded_files(dest)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
