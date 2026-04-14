"""Pure segmentation logic — OpenCV/numpy only, no Tk dependency."""

from __future__ import annotations

import cv2
import numpy as np


def preprocess_gray(image_rgb: np.ndarray, use_clahe: bool) -> np.ndarray:
    if image_rgb.shape[-1] == 3:
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_rgb

    if use_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return gray


def segment_ff(
    image_rgb: np.ndarray,
    x: int,
    y: int,
    sensitivity: int,
    edge_lock: bool,
    edge_lock_width: int,
    use_clahe: bool,
) -> np.ndarray | None:
    gray = preprocess_gray(image_rgb, use_clahe)
    h, w = gray.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    barrier = np.zeros((h, w), np.uint8)
    if edge_lock:
        edges = cv2.Canny(gray, 40, 120)
        k = max(1, min(5, int(edge_lock_width)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        barrier = cv2.dilate(edges, kernel, iterations=1)
        barrier = (barrier > 0).astype(np.uint8)
    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    ff_mask[0, :], ff_mask[-1, :], ff_mask[:, 0], ff_mask[:, -1] = 1, 1, 1, 1
    if edge_lock:
        ff_mask[1:-1, 1:-1][barrier == 1] = 1
    tol = max(1, min(80, 2 * int(sensitivity) + 2))
    img_ff = gray.copy()
    flags = cv2.FLOODFILL_MASK_ONLY | 4 | (255 << 8)
    try:
        _area, _, _, _ = cv2.floodFill(
            img_ff,
            ff_mask,
            seedPoint=(int(x), int(y)),
            newVal=0,
            loDiff=tol,
            upDiff=tol,
            flags=flags,
        )
    except cv2.error:
        return None
    region = (ff_mask[1:-1, 1:-1] == 255).astype(np.uint8)
    region = sanity_and_clean(region)
    return region


def segment_adaptive_cc(
    image_rgb: np.ndarray,
    x: int,
    y: int,
    sensitivity: int,
    use_clahe: bool,
) -> np.ndarray | None:
    gray = preprocess_gray(image_rgb, use_clahe)
    h, w = gray.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    block = max(11, 2 * (5 + int(sensitivity) // 2) + 1)
    c_value = max(2, min(15, 12 - int(sensitivity) // 5))
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, c_value
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel, iterations=1)
    labels = cv2.connectedComponentsWithStats(
        (thr > 0).astype(np.uint8), connectivity=8
    )[1]
    lbl = labels[int(y), int(x)]
    if lbl == 0:
        r = 3
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        patch = labels[y0:y1, x0:x1]
        u = np.unique(patch)
        u = u[u != 0]
        if u.size == 0:
            return None
        lbl = int(u[0])
    region = (labels == lbl).astype(np.uint8)
    region = sanity_and_clean(region)
    return region


def sanity_and_clean(mask: np.ndarray) -> np.ndarray | None:
    h, w = mask.shape[:2]
    area = int(mask.sum())
    if area < 30:
        return None
    if area > 0.7 * w * h:
        return None
    kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel2, iterations=1)
    return (mask > 0).astype(np.uint8)


def grow_shrink(mask: np.ndarray, steps: int) -> np.ndarray:
    if steps == 0:
        return (mask > 0).astype(np.uint8)
    k = min(25, max(1, abs(steps)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    if steps > 0:
        out = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1)
    else:
        out = cv2.erode(mask.astype(np.uint8), kernel, iterations=1)
    return (out > 0).astype(np.uint8)
