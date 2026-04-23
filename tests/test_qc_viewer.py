import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from qc_viewer import (
    load_summary,
    discover_annotator_files,
    get_shared_images,
    load_annotator_data,
    get_annotations_for_image,
    compute_landmark_distance,
    compute_pairwise_distances,
)


def test_load_summary(tmp_path):
    summary = {
        "rounds": [{"image_membership": {"img_a.tiff": ["g1", "g2"]}}],
        "group_mapping": {
            "g1": {"file": "r1_andrew.json", "annotator": "andrew"},
            "g2": {"file": "r1_mark.json", "annotator": "mark"},
        },
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    result = load_summary(path)
    assert result["rounds"][0]["image_membership"]["img_a.tiff"] == ["g1", "g2"]


def test_discover_annotator_files(tmp_path):
    summary = {
        "group_mapping": {
            "g1": {"file": "r1_andrew.json", "annotator": "andrew"},
            "g2": {"file": "r1_mark.json", "annotator": "mark"},
        }
    }
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "r1_andrew.json").write_text("{}")
    (data_dir / "r1_mark.json").write_text("{}")

    result = discover_annotator_files(summary, data_dir)
    assert set(result.keys()) == {"andrew", "mark"}
    assert result["andrew"] == data_dir / "r1_andrew.json"


def test_get_shared_images():
    summary = {
        "rounds": [
            {
                "image_membership": {
                    "img_a.tiff": ["g1", "g2", "g3"],
                    "img_b.tiff": ["g1"],
                    "img_c.tiff": ["g2", "g3"],
                }
            }
        ]
    }
    shared = get_shared_images(summary)
    assert "img_a.tiff" in shared
    assert "img_c.tiff" in shared
    assert "img_b.tiff" not in shared
    assert len(shared) == 2


def test_load_annotator_data(tmp_path):
    data = {
        "landmarks": ["L-ASIS", "R-ASIS"],
        "views": {"AP Bilateral": ["L-ASIS", "R-ASIS"]},
        "images": [
            {
                "image_path": "img_a.tiff",
                "image_flag": False,
                "view": "AP Bilateral",
                "image_direction": "AP",
                "annotations": {
                    "L-ASIS": {"value": [100.0, 200.0], "flag": False, "note": ""},
                    "R-ASIS": {"value": None, "flag": True, "note": "not visible"},
                },
            }
        ],
    }
    path = tmp_path / "annotator.json"
    path.write_text(json.dumps(data))

    result = load_annotator_data(path)
    assert result["landmarks"] == ["L-ASIS", "R-ASIS"]
    assert len(result["images"]) == 1


def test_get_annotations_for_image():
    annotator_data = {
        "images": [
            {
                "image_path": "img_a.tiff",
                "annotations": {
                    "L-ASIS": {"value": [100.0, 200.0], "flag": False},
                    "R-ASIS": {"value": None, "flag": True},
                },
            },
            {
                "image_path": "img_b.tiff",
                "annotations": {"L-ASIS": {"value": [300.0, 400.0], "flag": False}},
            },
        ]
    }
    result = get_annotations_for_image(annotator_data, "img_a.tiff")
    assert result["L-ASIS"]["value"] == [100.0, 200.0]
    assert result["R-ASIS"]["value"] is None


def test_landmark_distance_points():
    result = compute_landmark_distance([100.0, 200.0], [103.0, 204.0])
    assert result["type"] == "point"
    assert abs(result["distance"] - 5.0) < 0.01


def test_landmark_distance_lines():
    result = compute_landmark_distance(
        [[0.0, 0.0], [100.0, 0.0]],
        [[0.0, 10.0], [100.0, 10.0]],
    )
    assert result["type"] == "line"
    assert abs(result["signed_dists"][0] - (-10.0)) < 0.01
    assert abs(result["signed_dists"][1] - (-10.0)) < 0.01
    assert abs(result["angle_deg"] - 0.0) < 0.01


def test_landmark_distance_lines_angle():
    result = compute_landmark_distance(
        [[0.0, 0.0], [100.0, 0.0]],
        [[0.0, 0.0], [0.0, 100.0]],
    )
    assert result["type"] == "line"
    assert abs(result["angle_deg"] - 90.0) < 0.01


def test_landmark_distance_none():
    assert compute_landmark_distance(None, [100.0, 200.0]) is None
    assert compute_landmark_distance([100.0, 200.0], None) is None


def test_pairwise_distances():
    annotators = {
        "andrew": {
            "images": [
                {
                    "image_path": "img_a.tiff",
                    "annotations": {
                        "L-ASIS": {"value": [100.0, 200.0], "flag": False},
                        "R-ASIS": {"value": [300.0, 200.0], "flag": False},
                    },
                }
            ]
        },
        "mark": {
            "images": [
                {
                    "image_path": "img_a.tiff",
                    "annotations": {
                        "L-ASIS": {"value": [103.0, 204.0], "flag": False},
                        "R-ASIS": {"value": [305.0, 202.0], "flag": False},
                    },
                }
            ]
        },
    }
    distances = compute_pairwise_distances(annotators, "img_a.tiff", ["L-ASIS", "R-ASIS"])
    l_result = distances["L-ASIS"][("andrew", "mark")]
    assert l_result["type"] == "point"
    assert abs(l_result["distance"] - 5.0) < 0.01
    r_result = distances["R-ASIS"][("andrew", "mark")]
    assert r_result["type"] == "point"
    assert abs(r_result["distance"] - math.dist([300, 200], [305, 202])) < 0.01


def test_detect_mismatches_all_ok():
    from qc_viewer import detect_mismatches
    annotators = {
        "a": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": [100, 200], "flag": False}}}]},
        "b": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": [102, 201], "flag": False}}}]},
    }
    result = detect_mismatches(annotators, "img.tiff", ["L-ASIS"])
    assert result["L-ASIS"] == "ok"


def test_detect_mismatches_missing():
    from qc_viewer import detect_mismatches
    annotators = {
        "a": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": [100, 200], "flag": False}}}]},
        "b": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": None, "flag": False}}}]},
    }
    result = detect_mismatches(annotators, "img.tiff", ["L-ASIS"])
    assert result["L-ASIS"] == "missing"


def test_detect_mismatches_flagged():
    from qc_viewer import detect_mismatches
    annotators = {
        "a": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": [100, 200], "flag": False}}}]},
        "b": {"images": [{"image_path": "img.tiff", "annotations": {"L-ASIS": {"value": [102, 201], "flag": True}}}]},
    }
    result = detect_mismatches(annotators, "img.tiff", ["L-ASIS"])
    assert result["L-ASIS"] == "flagged"
