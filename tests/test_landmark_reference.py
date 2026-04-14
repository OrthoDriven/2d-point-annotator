"""Tests for landmark reference lookup logic."""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

import json
from pathlib import Path

import pytest

# landmark_reference.py lives in src/, so we need it on the path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from landmark_reference import LandmarkReference  # noqa: E402


@pytest.fixture()
def landmarks_json(tmp_path: Path) -> Path:
    """Create a minimal landmarks.json for testing."""
    data: dict[str, object] = {
        "metadata": {
            "version": "0.0.1",
            "product": "Test",
            "last_updated": "2026-01-01",
        },
        "landmarks": [
            {
                "name": "Femoral Head Center",
                "acronym": "FHC",
                "anatomical_feature": "Center of the femoral head",
                "views": ["AP"],
                "prediction_geometry": {
                    "type": "point",
                    "count": 2,
                    "labels": ["left", "right"],
                },
                "landmark_type": "primary",
                "placement_rules": {
                    "native": "Use the hover circle to approximate the visible bony femoral head.",
                    "prosthetic": "Fit to outer margin of the femoral head component.",
                },
                "edge_cases": None,
                "escalate_when": None,
            },
            {
                "name": "Pubic Symphysis",
                "acronym": "{S,I}PS",
                "anatomical_feature": None,
                "views": ["AP"],
                "prediction_geometry": {
                    "type": "point",
                    "count": 4,
                    "labels": ["rs", "ls", "ri", "li"],
                },
                "landmark_type": "primary",
                "placement_rules": {"general": "Select the four corner points."},
                "edge_cases": None,
                "escalate_when": None,
            },
            {
                "name": "Lesser Trochanter",
                "acronym": "{P,M,D}LT",
                "anatomical_feature": "Lesser trochanter junction",
                "views": ["AP"],
                "prediction_geometry": {"type": "point", "count": 6, "labels": []},
                "landmark_type": "primary",
                "placement_rules": {
                    "general": "Visualize as a volcano tipped 90 degrees."
                },
                "edge_cases": None,
                "escalate_when": None,
            },
            {
                "name": "Lateral Innominate Point",
                "acronym": "LIP",
                "anatomical_feature": "Lateral aspect of the pelvic wing",
                "views": ["AP"],
                "prediction_geometry": {
                    "type": "point",
                    "count": 2,
                    "labels": ["left", "right"],
                },
                "landmark_type": "primary",
                "placement_rules": {
                    "general": "Select the most lateral visible point."
                },
                "edge_cases": None,
                "escalate_when": None,
            },
        ],
    }
    p = tmp_path / "landmarks.json"
    p.write_text(json.dumps(data))
    return p


class TestLandmarkReference:
    """Test the LandmarkReference lookup API."""

    def test_direct_acronym_lookup(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("L-FHC")
        assert defn is not None
        assert defn["name"] == "Femoral Head Center"
        assert defn["acronym"] == "FHC"
        assert "native" in defn["placement_rules"]

    def test_right_prefix_lookup(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("R-FHC")
        assert defn is not None
        assert defn["name"] == "Femoral Head Center"

    def test_template_pubic_symphysis_sps(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("L-SPS")
        assert defn is not None
        assert defn["name"] == "Pubic Symphysis"

    def test_template_pubic_symphysis_ips(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("R-IPS")
        assert defn is not None
        assert defn["name"] == "Pubic Symphysis"

    def test_template_lesser_trochanter_plt(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("L-PLT")
        assert defn is not None
        assert defn["name"] == "Lesser Trochanter"

    def test_template_lesser_trochanter_mlt(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("R-MLT")
        assert defn is not None
        assert defn["name"] == "Lesser Trochanter"

    def test_template_lesser_trochanter_dlt(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("L-DLT")
        assert defn is not None
        assert defn["name"] == "Lesser Trochanter"

    def test_unknown_landmark_returns_none(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        assert ref.get_definition("L-NOPE") is None

    def test_no_prefix_returns_none(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        assert ref.get_definition("FHC") is None

    def test_get_all_definitions_order(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        all_defs = ref.get_all_definitions()
        assert len(all_defs) == 4
        assert all_defs[0]["name"] == "Femoral Head Center"
        assert all_defs[1]["name"] == "Pubic Symphysis"
        assert all_defs[2]["name"] == "Lesser Trochanter"
        assert all_defs[3]["name"] == "Lateral Innominate Point"

    def test_definition_omits_null_anatomy(self, landmarks_json: Path) -> None:
        ref = LandmarkReference(landmarks_json)
        defn = ref.get_definition("L-SPS")
        assert defn is not None
        assert defn["anatomical_feature"] is None

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            LandmarkReference(tmp_path / "nonexistent.json")
