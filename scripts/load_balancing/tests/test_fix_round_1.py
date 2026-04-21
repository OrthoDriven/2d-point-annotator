"""Tests for fix_round_1.py (Fixes 1, 2, 6, 7, 8)."""

import json
import random
import sys
from pathlib import Path

import pytest

from fix_round_1 import build_assignments, build_summary, load_backup, FOLDER_MAPPING
from helpers import ALL_IMAGES, LANDMARKS, VIEWS, _make_image_record


class TestFix1RandomSampling:
    def test_shared_pool_is_random_sample(self):
        annotated = set(ALL_IMAGES[:8])
        rng = random.Random(1234)
        _, shared_pool = build_assignments(
            ["andrew", "scott"], {"andrew": annotated, "scott": set()},
            ALL_IMAGES, 3, 5, rng,
        )
        assert set(shared_pool).issubset(annotated)
        assert len(shared_pool) == 3
        first_n = sorted(annotated)[:3]
        assert shared_pool != first_n


class TestFix2SeedInSummary:
    def test_seed_in_r1_summary(self, synthetic_backup_dir, synthetic_config_dir, tmp_path):
        from fix_round_1 import main as r1_main
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        sys.argv = ["fix_round_1", "--config", str(synthetic_config_dir / "fix_round_1.yaml"),
                     "--backup-dir", str(synthetic_backup_dir),
                     "--output-dir", str(output_dir), "--seed", "9999"]
        r1_main()
        summary = json.loads((output_dir / "fluoro-r1_round1_summary.json").read_text())
        assert summary["seed"] == 9999


class TestFix6DefensiveLoading:
    def test_missing_folder_logs_info(self, synthetic_backup_dir, capsys):
        result = load_backup("unknown", synthetic_backup_dir, "fluoro-r1")
        assert result is None
        captured = capsys.readouterr()
        assert "[info] no backup folder" in captured.out

    def test_missing_file_logs_info(self, synthetic_backup_dir, tmp_path, capsys):
        empty_dir = synthetic_backup_dir / "empty_annotator"
        empty_dir.mkdir()
        result = load_backup("empty_annotator", synthetic_backup_dir, "fluoro-r1")
        assert result is None
        captured = capsys.readouterr()
        assert "[info] backup folder exists but no file" in captured.out

    def test_custom_folder_mapping(self, synthetic_backup_dir):
        custom_mapping = {"andrew": "ajj", "scott": "SAB"}
        result = load_backup("andrew", synthetic_backup_dir, "fluoro-r1", custom_mapping)
        assert result is not None
        assert "landmarks" in result


class TestFix7MinTotalN:
    def test_new_key_works(self, synthetic_backup_dir, tmp_path):
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config = {
            "backup_dir": str(synthetic_backup_dir),
            "backup_summary": str(synthetic_backup_dir / "fluoro-r1_summary.json"),
            "output_dir": str(tmp_path / "output"),
            "annotators": ["scott", "andrew", "mark", "paris"],
            "shared_pool_size": 3,
            "min_total_n": 5,
            "prefix": "fluoro-r1",
            "seed": 1234,
        }
        path = config_dir / "fix_round_1.yaml"
        path.write_text("\n".join(f"{k}: {json.dumps(v)}" for k, v in config.items()))
        from config_loader import load_config
        cfg = load_config(path)
        assert cfg["min_total_n"] == 5

    def test_old_key_with_warning(self, synthetic_backup_dir, tmp_path, capsys):
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config = {
            "backup_dir": str(synthetic_backup_dir),
            "backup_summary": str(synthetic_backup_dir / "fluoro-r1_summary.json"),
            "output_dir": str(tmp_path / "output"),
            "annotators": ["scott", "andrew", "mark", "paris"],
            "shared_pool_size": 3,
            "target_n": 5,
            "prefix": "fluoro-r1",
            "seed": 1234,
        }
        path = config_dir / "fix_round_1.yaml"
        path.write_text("\n".join(f"{k}: {json.dumps(v)}" for k, v in config.items()))
        sys.argv = ["fix_round_1", "--config", str(path)]
        from fix_round_1 import main as r1_main
        r1_main()
        captured = capsys.readouterr()
        assert "deprecated" in captured.out


class TestFix8TemplateDrift:
    def test_drift_detected(self, synthetic_backup_dir):
        mark_path = synthetic_backup_dir / "mark" / "fluoro-r1_mark.json"
        data = json.loads(mark_path.read_text())
        data["landmarks"] = ["DIFFERENT"]
        mark_path.write_text(json.dumps(data))
        from fix_round_1 import load_all_images_from_backup_summary
        from config_loader import load_config
        all_images = load_all_images_from_backup_summary(
            synthetic_backup_dir / "fluoro-r1_summary.json"
        )
        raw_data = {}
        for ann in ["scott", "andrew", "mark", "paris"]:
            raw_data[ann] = load_backup(ann, synthetic_backup_dir, "fluoro-r1")
        with pytest.raises(RuntimeError, match="template drift"):
            templates = [(a, d) for a, d in raw_data.items() if d is not None]
            if len(templates) > 1:
                ref_ann, ref = templates[0]
                for ann, d in templates[1:]:
                    if d["landmarks"] != ref["landmarks"] or d["views"] != ref["views"]:
                        raise RuntimeError(
                            f"Backup template drift: {ann} landmarks/views differ from {ref_ann}. "
                            f"Investigate before regenerating."
                        )

    def test_no_drift_passes(self, synthetic_backup_dir):
        raw_data = {}
        for ann in ["scott", "andrew", "mark", "paris"]:
            raw_data[ann] = load_backup(ann, synthetic_backup_dir, "fluoro-r1")
        templates = [(a, d) for a, d in raw_data.items() if d is not None]
        if len(templates) > 1:
            ref_ann, ref = templates[0]
            for ann, d in templates[1:]:
                assert d["landmarks"] == ref["landmarks"]
                assert d["views"] == ref["views"]
