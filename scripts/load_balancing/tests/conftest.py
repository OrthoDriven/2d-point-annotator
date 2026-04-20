"""Shared fixtures for load-balancing test suite."""

import json
import sys
from pathlib import Path

import pytest

_test_dir = str(Path(__file__).resolve().parent)
_lb_dir = str(Path(__file__).resolve().parent.parent)
for _d in [_test_dir, _lb_dir]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

from helpers import LANDMARKS, VIEWS, ALL_IMAGES, _make_image_record


@pytest.fixture()
def synthetic_backup_dir(tmp_path: Path) -> Path:
    """Create synthetic remote_backups/ tree with 4 annotators, 10 images."""
    backup = tmp_path / "remote_backups"
    backup.mkdir()

    annotator_data = {
        "andrew": {"folder": "ajj", "annotated_indices": [0, 1, 2, 3, 4, 5, 6, 7]},
        "scott":  {"folder": "SAB",  "annotated_indices": [0, 1, 8]},
        "mark":   {"folder": "mark", "annotated_indices": [2, 9]},
        "paris":  {"folder": "paris", "annotated_indices": []},
    }

    for ann, info in annotator_data.items():
        folder = backup / info["folder"]
        folder.mkdir(parents=True, exist_ok=True)

        images = []
        for i, img in enumerate(ALL_IMAGES):
            annotated = i in info["annotated_indices"]
            images.append(_make_image_record(img, annotated))

        data = {
            "landmarks": LANDMARKS,
            "views": VIEWS,
            "images": images,
        }
        path = folder / f"fluoro-r1_{ann}.json"
        path.write_text(json.dumps(data, indent=2))

    summary = {
        "total_original_images": len(ALL_IMAGES),
        "image_membership": {img: ["group_1"] for img in ALL_IMAGES},
    }
    (backup / "fluoro-r1_summary.json").write_text(json.dumps(summary, indent=2))

    return backup


@pytest.fixture()
def synthetic_config_dir(tmp_path: Path) -> Path:
    """Create config directory with fix_round_1.yaml."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    config = {
        "backup_dir": str(tmp_path / "remote_backups"),
        "backup_summary": str(tmp_path / "remote_backups" / "fluoro-r1_summary.json"),
        "output_dir": str(tmp_path / "output"),
        "annotators": ["scott", "andrew", "mark", "paris"],
        "shared_pool_size": 3,
        "min_total_n": 5,
        "prefix": "fluoro-r1",
        "seed": 1234,
    }
    path = config_dir / "fix_round_1.yaml"
    path.write_text("\n".join(f"{k}: {json.dumps(v)}" for k, v in config.items()))

    return config_dir


@pytest.fixture()
def round1_summary_and_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal Round 1 output for build_future_rounds testing."""
    output_dir = tmp_path / "r1_output"
    output_dir.mkdir()

    r1_images = {
        "andrew": ALL_IMAGES[:5],
        "scott":  ALL_IMAGES[2:7],
        "mark":   ALL_IMAGES[4:9],
        "paris":  ALL_IMAGES[5:10],
    }

    group_mapping = {}
    for i, ann in enumerate(["andrew", "scott", "mark", "paris"]):
        group = f"group_{i+1}"
        fname = f"fluoro-r1_round1_{ann}.json"
        group_mapping[group] = {"file": fname, "annotator": ann}

        images = [_make_image_record(img) for img in r1_images[ann]]
        data = {"landmarks": LANDMARKS, "views": VIEWS, "images": images}
        (output_dir / fname).write_text(json.dumps(data, indent=2))

    r1_universe = sorted(set().union(*r1_images.values()))
    shared_pool = ALL_IMAGES[2:5]

    round_data = {
        "round": 1,
        "total_original_images_in_round": len(r1_universe),
        "round_images": r1_universe,
        "shared_pool_images": shared_pool,
        "group_mapping": group_mapping,
    }
    summary = {
        "total_original_images": len(ALL_IMAGES),
        "num_rounds": 1,
        "group_mapping": group_mapping,
        "rounds": [round_data],
    }
    summary_path = output_dir / "fluoro-r1_round1_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    backup_summary = {
        "total_original_images": len(ALL_IMAGES),
        "image_membership": {img: ["group_1"] for img in ALL_IMAGES},
    }
    (tmp_path / "fluoro-r1_summary.json").write_text(json.dumps(backup_summary, indent=2))

    return summary_path, output_dir
