#!/usr/bin/env python3

"""Tests for the global auto-merge system."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from auto_merge import auto_merge_on_load, _get_annotated_images, _merge_image_lists


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_image(path: str, annotations=None, view=None, flag=False):
    """Build a minimal image record."""
    return {
        "image_path": path,
        "image_flag": flag,
        "view": view,
        "annotations": annotations or {},
    }


def make_json_file(path: Path, images, landmarks=None, views=None):
    """Write a JSON annotation file."""
    data = {
        "landmarks": landmarks or ["L-LIP", "R-LIP"],
        "views": views or {"AP Bilateral": ["L-LIP", "R-LIP"]},
        "images": images,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# _get_annotated_images
# ---------------------------------------------------------------------------

class TestGetAnnotatedImages:
    def test_empty_list(self):
        assert _get_annotated_images([]) == set()

    def test_unannotated_image(self):
        images = [make_image("a.tif")]
        assert _get_annotated_images(images) == set()

    def test_image_with_annotation_value(self):
        images = [make_image("a.tif", annotations={"L-LIP": {"value": [10, 20]}})]
        assert _get_annotated_images(images) == {"a.tif"}

    def test_image_with_view(self):
        images = [make_image("a.tif", view="AP Bilateral")]
        assert _get_annotated_images(images) == {"a.tif"}

    def test_image_with_flag(self):
        images = [make_image("a.tif", flag=True)]
        assert _get_annotated_images(images) == {"a.tif"}

    def test_mixed(self):
        images = [
            make_image("a.tif"),  # blank
            make_image("b.tif", annotations={"L-LIP": {"value": [1, 2]}}),  # annotated
            make_image("c.tif"),  # blank
        ]
        assert _get_annotated_images(images) == {"b.tif"}


# ---------------------------------------------------------------------------
# _merge_image_lists
# ---------------------------------------------------------------------------

class TestMergeImageLists:
    def test_no_changes(self):
        """Same list in, same list out (no adds or removes)."""
        local = [make_image("a.tif"), make_image("b.tif")]
        source = [make_image("a.tif"), make_image("b.tif")]
        merged, stats = _merge_image_lists(local, source)
        assert stats["added"] == 0
        assert stats["removed"] == 0
        assert len(merged) == 2

    def test_new_images_from_source(self):
        """Source has a new image — it gets added."""
        local = [make_image("a.tif")]
        source = [make_image("a.tif"), make_image("b.tif")]
        merged, stats = _merge_image_lists(local, source)
        assert stats["added"] == 1
        paths = {r["image_path"] for r in merged}
        assert "b.tif" in paths

    def test_annotated_image_kept_even_if_removed_from_source(self):
        """Annotated images are never dropped."""
        local = [
            make_image("a.tif", annotations={"L-LIP": {"value": [1, 2]}}),
            make_image("b.tif"),
        ]
        source = [make_image("b.tif")]  # a.tif removed from source
        merged, stats = _merge_image_lists(local, source)
        paths = {r["image_path"] for r in merged}
        assert "a.tif" in paths  # kept because annotated
        assert stats["kept"] == 1

    def test_unannotated_image_removed_if_not_in_source(self):
        """Unannotated images not in source get dropped."""
        local = [make_image("a.tif"), make_image("b.tif")]
        source = [make_image("a.tif")]  # b.tif removed from source
        merged, stats = _merge_image_lists(local, source)
        paths = {r["image_path"] for r in merged}
        assert "b.tif" not in paths
        assert stats["removed"] == 1

    def test_annotations_preserved_for_existing_images(self):
        """Annotations from local are preserved, not overwritten by source."""
        local = [
            make_image("a.tif", annotations={"L-LIP": {"value": [10, 20]}}),
        ]
        source = [
            make_image("a.tif", annotations={}),  # source has blank
        ]
        merged, stats = _merge_image_lists(local, source)
        a_record = next(r for r in merged if r["image_path"] == "a.tif")
        assert a_record["annotations"]["L-LIP"]["value"] == [10, 20]

    def test_source_metadata_used_for_new_images(self):
        """New images come from source, preserving source metadata."""
        local = []
        source = [make_image("a.tif")]
        merged, stats = _merge_image_lists(local, source)
        assert stats["added"] == 1
        assert merged[0]["image_path"] == "a.tif"


# ---------------------------------------------------------------------------
# auto_merge_on_load (integration)
# ---------------------------------------------------------------------------

class TestAutoMergeOnLoad:
    def test_no_matching_source(self, tmp_path):
        """When no source file exists, local is returned unchanged."""
        local = tmp_path / "data.json"
        make_json_file(local, [make_image("a.tif")])

        with patch("auto_merge.SOURCE_DATA_DIR", tmp_path / "nonexistent"):
            result = auto_merge_on_load(local)

        assert len(result["images"]) == 1
        assert result["images"][0]["image_path"] == "a.tif"

    def test_source_has_new_images(self, tmp_path):
        """New images from source get merged into local."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(local_file, [make_image("a.tif")])
        make_json_file(source_file, [make_image("a.tif"), make_image("b.tif"), make_image("c.tif")])

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        paths = {r["image_path"] for r in result["images"]}
        assert paths == {"a.tif", "b.tif", "c.tif"}

    def test_annotations_never_overwritten(self, tmp_path):
        """Annotations survive the merge even if source has blank versions."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        annotated = make_image(
            "a.tif",
            annotations={"L-LIP": {"value": [100, 200], "flag": True, "note": "done"}},
        )
        make_json_file(local_file, [annotated])
        make_json_file(source_file, [make_image("a.tif"), make_image("b.tif")])

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        a_record = next(r for r in result["images"] if r["image_path"] == "a.tif")
        assert a_record["annotations"]["L-LIP"]["value"] == [100, 200]
        assert a_record["annotations"]["L-LIP"]["flag"] is True
        assert a_record["annotations"]["L-LIP"]["note"] == "done"

    def test_annotated_image_kept_when_removed_from_source(self, tmp_path):
        """If source drops an image but local has it annotated, it stays."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(local_file, [
            make_image("a.tif", annotations={"L-LIP": {"value": [1, 2]}}),
            make_image("b.tif"),
        ])
        make_json_file(source_file, [make_image("c.tif")])  # a and b removed

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        paths = {r["image_path"] for r in result["images"]}
        assert "a.tif" in paths  # annotated — kept
        assert "b.tif" not in paths  # unannotated — dropped
        assert "c.tif" in paths  # new from source

    def test_landmarks_and_views_from_source(self, tmp_path):
        """Landmarks and views propagate from source."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(
            local_file,
            [make_image("a.tif")],
            landmarks=["OLD-LM"],
            views={"Old View": ["OLD-LM"]},
        )
        make_json_file(
            source_file,
            [make_image("a.tif")],
            landmarks=["NEW-LM", "NEW-LM2"],
            views={"New View": ["NEW-LM", "NEW-LM2"]},
        )

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        assert result["landmarks"] == ["NEW-LM", "NEW-LM2"]
        assert result["views"] == {"New View": ["NEW-LM", "NEW-LM2"]}

    def test_merge_written_back_to_disk(self, tmp_path):
        """After merge, the local file on disk has the merged content."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(local_file, [make_image("a.tif")])
        make_json_file(source_file, [make_image("a.tif"), make_image("b.tif")])

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            auto_merge_on_load(local_file)

        # Re-read from disk
        saved = json.loads(local_file.read_text(encoding="utf-8"))
        paths = {r["image_path"] for r in saved["images"]}
        assert paths == {"a.tif", "b.tif"}

    def test_no_merge_when_images_match(self, tmp_path):
        """When image lists are identical, no merge happens (file unchanged)."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        images = [make_image("a.tif"), make_image("b.tif")]
        make_json_file(local_file, images)
        make_json_file(source_file, images)

        original_content = local_file.read_text(encoding="utf-8")

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            auto_merge_on_load(local_file)

        # File should not have been rewritten
        assert local_file.read_text(encoding="utf-8") == original_content

    def test_metadata_change_log_updated(self, tmp_path):
        """Merge adds a change_log entry to metadata."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(local_file, [make_image("a.tif")])
        make_json_file(source_file, [make_image("a.tif"), make_image("b.tif")])

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        log = result.get("metadata", {}).get("change_log", [])
        assert len(log) == 1
        assert log[0]["action"] == "auto_merge"
        assert "added" in log[0]["details"]

    def test_malformed_source_returns_local(self, tmp_path):
        """If source JSON is broken, local is returned unchanged."""
        local_dir = tmp_path / "local"
        source_dir = tmp_path / "source"
        local_dir.mkdir()
        source_dir.mkdir()

        local_file = local_dir / "data.json"
        source_file = source_dir / "data.json"

        make_json_file(local_file, [make_image("a.tif")])
        source_file.write_text("NOT VALID JSON{{{")

        with patch("auto_merge.SOURCE_DATA_DIR", source_dir):
            result = auto_merge_on_load(local_file)

        assert len(result["images"]) == 1
