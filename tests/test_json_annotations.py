#!/usr/bin/env python3

# pyright: reportMissingImports=false

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import AnnotationGUI


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def make_gui_stub(tmp_path: Path):
    gui = AnnotationGUI.__new__(AnnotationGUI)
    gui.json_path = tmp_path / "annotations.json"
    gui.json_dir = tmp_path
    gui.json_data = {"landmarks": [], "views": {}, "images": []}
    gui.image_index_map = {}
    gui.images = []
    gui.landmarks = ["L-FA", "LOB", "RKNEE"]
    gui.line_landmarks = {"L-FA", "R-FA"}
    gui.annotations = {}
    gui.lm_settings = {}
    gui.landmark_meta = {}
    gui.current_image_path = tmp_path / "image.png"
    gui.current_image_quality = 0
    gui.current_image_flag = True
    gui.current_view_var = FakeVar("ap")
    gui.saved_image_snapshots = {}
    gui.method = FakeVar("Flood Fill")
    gui.fill_sensitivity = FakeVar(18)
    gui.edge_lock = FakeVar(True)
    gui.edge_lock_width = FakeVar(2)
    gui.use_clahe = FakeVar(True)
    gui.grow_shrink = FakeVar(3)
    return gui


def test_parse_annotations_for_record_extracts_meta_and_segmentation_settings(tmp_path):
    gui = make_gui_stub(tmp_path)

    record = {
        "annotations": {
            "L-FA": {"value": [[1, 2], [3, 4]], "flag": True, "note": "shaft"},
            "LOB": {"value": [10, 20, "ACC", 7, 1, 5, 0, 2], "flag": False, "note": ""},
            "RKNEE": [30, 40],
        }
    }

    parsed = gui._parse_annotations_for_record(record)

    assert parsed == {
        "L-FA": [(1.0, 2.0), (3.0, 4.0)],
        "LOB": (10.0, 20.0),
        "RKNEE": (30.0, 40.0),
    }
    key = gui._path_key(gui.current_image_path)
    assert gui.landmark_meta[key]["L-FA"] == {"flag": True, "note": "shaft"}
    assert gui.landmark_meta[key]["RKNEE"] == {"flag": False, "note": ""}
    assert gui.lm_settings[key]["LOB"] == {
        "method": "Adaptive CC",
        "sens": 7,
        "edge_lock": 1,
        "edge_width": 5,
        "clahe": 0,
        "grow": 2,
    }


def test_prepare_landmark_data_includes_meta_and_line_landmarks(tmp_path):
    gui = make_gui_stub(tmp_path)
    key = gui._path_key(gui.current_image_path)
    gui.annotations[key] = {
        "L-FA": [(1.0, 2.0), (3.0, 4.0)],
        "LOB": (10.0, 20.0),
    }
    gui.lm_settings[key] = {
        "LOB": {
            "method": "Flood Fill",
            "sens": 9,
            "edge_lock": 1,
            "edge_width": 3,
            "clahe": 1,
            "grow": 4,
        }
    }
    gui.landmark_meta[key] = {
        "L-FA": {"flag": True, "note": "line note"},
        "RKNEE": {"flag": False, "note": "missing point note"},
    }

    data = gui._prepare_landmark_data()

    assert data == {
        "L-FA": {
            "value": [[1.0, 2.0], [3.0, 4.0]],
            "flag": True,
            "note": "line note",
        },
        "LOB": {
            "value": [10.0, 20.0, "FF", 9, 1, 3, 1, 4],
            "flag": False,
            "note": "",
        },
        "RKNEE": {
            "value": None,
            "flag": False,
            "note": "missing point note",
        },
    }


def test_current_image_has_unsaved_changes_uses_json_snapshot(tmp_path):
    gui = make_gui_stub(tmp_path)
    image_path = gui.current_image_path
    key = gui._path_key(image_path)
    gui.json_data["images"] = [
        {
            "image_path": "image.png",
            "image_flag": False,
            "view": "ap",
            "annotations": {},
            "resolved_image_path": key,
        }
    ]
    gui.image_index_map[key] = 0

    assert gui._current_image_has_unsaved_changes() is True

    gui.current_image_flag = False
    assert gui._current_image_has_unsaved_changes() is False

    gui.saved_image_snapshots[key] = json.dumps(
        {
            "image_path": "image.png",
            "image_flag": False,
            "view": "ap",
            "annotations": {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    gui.current_view_var.set("lat")
    assert gui._current_image_has_unsaved_changes() is True
