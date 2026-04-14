"""Pure geometry/coordinate math — no Tk dependency."""

from __future__ import annotations


def img_to_screen(
    xi: float, yi: float, scale: float, off_x: float, off_y: float
) -> tuple[float, float]:
    return off_x + xi * scale, off_y + yi * scale


def screen_to_img(
    xs: float, ys: float, scale: float, off_x: float, off_y: float
) -> tuple[float, float]:
    s = scale or 1.0
    return (xs - off_x) / s, (ys - off_y) / s


def display_rect(
    scale: float, off_x: float, off_y: float, disp_w: float, disp_h: float
) -> tuple[int, int, int, int]:
    _ = scale
    return int(off_x), int(off_y), int(off_x + disp_w), int(off_y + disp_h)


def clamp_img_point(
    xi: float, yi: float, img_w: int, img_h: int
) -> tuple[float, float]:
    xi = min(max(xi, 0.0), float(img_w - 1))
    yi = min(max(yi, 0.0), float(img_h - 1))
    return float(round(xi, 1)), float(round(yi, 1))


def point_to_segment_distance_px(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    vx = x2 - x1
    vy = y2 - y1
    seg_len2 = vx * vx + vy * vy

    if seg_len2 <= 1e-12:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5

    t = ((px - x1) * vx + (py - y1) * vy) / seg_len2
    t = max(0.0, min(1.0, t))

    proj_x = x1 + t * vx
    proj_y = y1 + t * vy
    return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5


def is_line_landmark(lm: str, line_landmarks: set[str]) -> bool:
    return lm in line_landmarks
