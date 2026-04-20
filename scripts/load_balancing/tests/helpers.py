"""Shared constants for load-balancing tests."""

LANDMARKS = ["L-ASIS", "R-ASIS", "L-PSIS", "R-PSIS"]
VIEWS = {"AP Bilateral": ["L-ASIS", "R-ASIS"], "PA Bilateral": ["L-PSIS", "R-PSIS"]}

ALL_IMAGES = [f"img_{i:05d}.tiff" for i in range(10)]


def _make_image_record(img_path: str, annotated: bool = False) -> dict:
    rec = {
        "image_path": img_path,
        "image_flag": False,
        "view": "AP Bilateral" if annotated else None,
        "image_direction": "AP" if annotated else None,
        "annotations": {},
    }
    if annotated:
        rec["annotations"] = {
            "L-ASIS": {"value": [100.0, 200.0], "flag": False, "note": ""},
            "R-ASIS": {"value": [300.0, 400.0], "flag": False, "note": ""},
        }
    return rec
