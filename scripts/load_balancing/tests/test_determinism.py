"""Tests for deterministic output (same seed = byte-identical)."""

import json
import sys
from pathlib import Path

import pytest

from helpers import ALL_IMAGES


def test_fix_round_1_deterministic(synthetic_backup_dir, synthetic_config_dir, tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    for d in [out1, out2]:
        sys.argv = ["fix_round_1", "--config", str(synthetic_config_dir / "fix_round_1.yaml"),
                     "--backup-dir", str(synthetic_backup_dir),
                     "--output-dir", str(d), "--seed", "1234"]
        from fix_round_1 import main as r1_main
        r1_main()

    for ann in ["scott", "andrew", "mark", "paris"]:
        f1 = out1 / f"fluoro-r1_round1_{ann}.json"
        f2 = out2 / f"fluoro-r1_round1_{ann}.json"
        assert f1.read_text() == f2.read_text()

    s1 = out1 / "fluoro-r1_round1_summary.json"
    s2 = out2 / "fluoro-r1_round1_summary.json"
    assert s1.read_text() == s2.read_text()


def test_build_future_rounds_deterministic(round1_summary_and_files, tmp_path):
    summary_path, output_dir = round1_summary_and_files
    backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"

    runs = []
    for _ in range(2):
        from build_future_rounds import load_round1_data, generate_rounds, build_summary
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 5678)
        runs.append(rounds)

    for r1, r2 in zip(runs[0], runs[1]):
        assert r1["round_num"] == r2["round_num"]
        for ann in r1["assignments"]:
            recs1 = [(rec["image_path"], rec["role"]) for rec in r1["assignments"][ann]]
            recs2 = [(rec["image_path"], rec["role"]) for rec in r2["assignments"][ann]]
            assert recs1 == recs2
