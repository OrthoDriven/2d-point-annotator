"""Landmark reference lookup: load docs/landmarks.json and resolve data landmark names to definitions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict, cast


class LandmarkDefinition(TypedDict):
    """Subset of landmark definition fields needed by the lookup API."""

    name: str
    acronym: str
    anatomical_feature: str | None
    placement_rules: dict[str, str]


class LandmarkReference:
    """Load landmark definitions and resolve data landmark names (e.g. 'L-FHC') to their definitions."""

    _TEMPLATE_RE: re.Pattern[str] = re.compile(r"^\{([A-Z,]+)\}(.+)$")

    def __init__(self, json_path: Path) -> None:
        if not json_path.exists():
            raise FileNotFoundError(f"Landmark definitions not found: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = cast(dict[str, object], json.load(f))

        metadata = cast(dict[str, object], data.get("metadata", {}))
        self._version: str = cast(str, metadata.get("version", "N/A"))

        self._definitions: list[LandmarkDefinition] = []
        self._index: dict[str, LandmarkDefinition] = {}

        landmarks = cast(list[dict[str, object]], data["landmarks"])

        for lm in landmarks:
            defn: LandmarkDefinition = {
                "name": cast(str, lm["name"]),
                "acronym": cast(str, lm["acronym"]),
                "anatomical_feature": cast(str | None, lm.get("anatomical_feature")),
                "placement_rules": cast(dict[str, str], lm["placement_rules"]),
            }
            self._definitions.append(defn)

            # Expand template acronyms like {S,I}PS -> SPS, IPS
            acronym = defn["acronym"]
            m = self._TEMPLATE_RE.match(acronym)
            if m:
                prefixes = m.group(1).split(",")
                suffix = m.group(2)
                for prefix in prefixes:
                    self._index[prefix + suffix] = defn
            else:
                self._index[acronym] = defn

    @property
    def version(self) -> str:
        """Protocol version from landmarks.json metadata."""
        return self._version

    def get_definition(self, landmark_name: str) -> LandmarkDefinition | None:
        """Look up a data landmark name (e.g. 'L-FHC') and return its definition, or None."""
        if not (landmark_name.startswith("L-") or landmark_name.startswith("R-")):
            return None
        base = landmark_name[2:]
        return self._index.get(base)

    def get_all_definitions(self) -> list[LandmarkDefinition]:
        """Return all landmark definitions in document order."""
        return list(self._definitions)
