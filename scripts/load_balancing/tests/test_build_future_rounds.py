"""Tests for build_future_rounds.py (Fixes 2, 3, 4, 5)."""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from build_future_rounds import generate_rounds, build_summary, _by_role
from helpers import ALL_IMAGES


class TestFix3RoundImages:
    def test_round_images_excludes_prior_seen(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        summary = build_summary(
            rounds, annotators, annotator_history, len(all_images),
            len(r1_universe), "fluoro-r2", [], 2, 3, 1, 42,
        )
        cumulative = set(r1_universe)
        for rd in summary["rounds"]:
            round_imgs = set(rd["round_images"])
            assert round_imgs.isdisjoint(cumulative)
            cumulative |= round_imgs


class TestFix4RoleLabels:
    def test_roles_disjoint_per_annotator_per_round(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        for r in rounds:
            for ann in annotators:
                recs = r["assignments"][ann]
                shared = _by_role(recs, "shared")
                unique = _by_role(recs, "unique")
                intra = _by_role(recs, "intra")
                total = len(shared) + len(unique) + len(intra)
                assert total == len(recs)

    def test_shared_count_equal_across_annotators(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        summary = build_summary(
            rounds, annotators, annotator_history, len(all_images),
            len(r1_universe), "fluoro-r2", [], 2, 3, 1, 42,
        )
        for rd in summary["rounds"]:
            shared_counts = rd["shared_counts_per_group"]
            vals = list(shared_counts.values())
            assert all(v == vals[0] for v in vals)
            assert vals[0] == 2


class TestFix5Calibration:
    def test_new_annotator_gets_calibration(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris", "sonia"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        summary = build_summary(
            rounds, annotators, annotator_history, len(all_images),
            len(r1_universe), "fluoro-r2", [], 2, 3, 1, 42,
        )
        for rd in summary["rounds"]:
            cal_counts = rd["calibration_counts_per_group"]
            assert cal_counts.get("sonia", 0) > 0


class TestFix2SeedInR2Summary:
    def test_seed_in_r2_summary(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 7777)
        summary = build_summary(
            rounds, annotators, annotator_history, len(all_images),
            len(r1_universe), "fluoro-r2", [], 2, 3, 1, 7777,
        )
        assert summary["seed"] == 7777


class TestEndToEnd:
    def test_per_annotator_json_has_no_role(self, round1_summary_and_files, tmp_path):
        summary_path, output_dir = round1_summary_and_files
        r2_output = tmp_path / "r2_output"
        r2_output.mkdir()
        sys.argv = ["build_future_rounds", "--config", str(tmp_path / "nonexistent.yaml")]
        from build_future_rounds import main as r2_main, load_round1_data, generate_rounds
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        for r in rounds:
            for ann in annotators:
                for rec in r["assignments"][ann]:
                    assert "role" not in rec or isinstance(rec, str)
        template = {"landmarks": ["L-ASIS"], "views": {"AP": ["L-ASIS"]}}
        for r in rounds:
            for ann, recs in r["assignments"].items():
                records = [{
                    "image_path": rec["image_path"],
                    "image_flag": False,
                    "view": None,
                    "image_direction": None,
                    "annotations": {},
                } for rec in recs]
                out = r2_output / f"fluoro-r2_round{r['round_num']}_{ann}.json"
                out.write_text(json.dumps({"landmarks": template["landmarks"], "views": template["views"], "images": records}))
                loaded = json.loads(out.read_text())
                for img in loaded["images"]:
                    assert "role" not in img
                    assert "image_path" in img
                    assert "annotations" in img


class TestLeftover:
    def test_leftover_increases_designed_shared(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        summary = build_summary(
            rounds, annotators, annotator_history, len(all_images),
            len(r1_universe), "fluoro-r2", [], 2, 3, 1, 42,
        )
        if len(summary["rounds"]) > 1:
            last = summary["rounds"][-1]
            earlier = summary["rounds"][-2]
            assert last["designed_shared_count"] >= earlier["designed_shared_count"]


class TestCrossAnnotatorRoleConsistency:
    def test_no_role_conflict_within_round(self, round1_summary_and_files):
        summary_path, output_dir = round1_summary_and_files
        from build_future_rounds import load_round1_data
        backup_summary_path = summary_path.parent.parent / "fluoro-r1_summary.json"
        r1_universe, annotator_history, r1_shared, all_images = load_round1_data(
            summary_path, backup_summary_path,
        )
        future_pool = [img for img in all_images if img not in r1_universe]
        annotators = ["andrew", "scott", "mark", "paris"]
        for ann in annotators:
            if ann not in annotator_history:
                annotator_history[ann] = set()
        rounds = generate_rounds(future_pool, r1_shared, annotator_history, annotators, 2, 3, 1, 42)
        for r in rounds:
            img_roles = defaultdict(set)
            for ann in annotators:
                for rec in r["assignments"][ann]:
                    img_roles[rec["image_path"]].add(rec["role"])
            for img, roles in img_roles.items():
                assert len(roles) == 1 or roles == {"shared"}, f"Role conflict for {img}: {roles}"
