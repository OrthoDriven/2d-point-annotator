"""Femoral axis tool — overlay projections along femoral axis line landmarks."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import logging
import math
import tkinter as tk
from typing import Protocol


class _BoolVarLike(Protocol):
    def get(self) -> bool: ...

    def set(self, value: bool) -> None: ...


class _IntVarLike(Protocol):
    def get(self) -> int: ...

    def set(self, value: int) -> None: ...


class _StrVarLike(Protocol):
    def get(self) -> str: ...


class _Configurable(Protocol):
    def config(self, *args: object, **kwargs: object) -> None: ...


class AnnotationGUI(Protocol):
    hover_enabled: _BoolVarLike
    femoral_axis_enabled: _BoolVarLike
    femoral_axis_count: _IntVarLike
    femoral_axis_proj_length: _IntVarLike
    femoral_axis_whisker_tip_length: _IntVarLike
    selected_landmark: _StrVarLike
    radius_scale: _Configurable
    femoral_axis_count_scale: _Configurable
    femoral_axis_whisker_tip_length_scale: _Configurable
    canvas: tk.Canvas
    current_image: object | None
    last_mouse_canvas_pos: tuple[int, int] | None
    femoral_axis_item_ids: list[int]

    def _hide_hover_circle(self) -> None: ...

    def _get_line_points(self, lm: str) -> list[tuple[float, float]]: ...

    def _img_to_screen(self, xi: float, yi: float) -> tuple[float, float]: ...

    def _display_rect(self) -> tuple[int, int, int, int]: ...


logger = logging.getLogger(__name__)


def change_femoral_axis_length(gui: AnnotationGUI, delta: int) -> None:
    new_len = max(2, min(300, int(gui.femoral_axis_proj_length.get()) + delta))
    if new_len != gui.femoral_axis_proj_length.get():
        gui.femoral_axis_proj_length.set(new_len)
        update_femoral_axis_overlay(gui)


def toggle_femoral_axis(gui: AnnotationGUI) -> None:
    enabled = gui.femoral_axis_enabled.get()
    gui.femoral_axis_count_scale.config(state="normal" if enabled else "disabled")
    gui.femoral_axis_whisker_tip_length_scale.config(
        state="normal" if enabled else "disabled"
    )

    if enabled and gui.hover_enabled.get():
        gui.hover_enabled.set(False)
        gui.radius_scale.config(state="disabled")
        gui._hide_hover_circle()

    if not enabled:
        clear_femoral_axis_overlay(gui)
    else:
        update_femoral_axis_overlay(gui)


def on_femoral_axis_whisker_tip_length_change(gui: AnnotationGUI, _value: str) -> None:
    if not gui.femoral_axis_enabled.get():
        return
    new_len = max(1, min(80, int(gui.femoral_axis_whisker_tip_length.get())))
    gui.femoral_axis_whisker_tip_length.set(new_len)
    update_femoral_axis_overlay(gui)


def on_femoral_axis_count_change(gui: AnnotationGUI, _value: str) -> None:
    if not gui.femoral_axis_enabled.get():
        return
    count = max(1, min(20, int(gui.femoral_axis_count.get())))
    gui.femoral_axis_count.set(count)
    update_femoral_axis_overlay(gui)


def clear_femoral_axis_overlay(gui: AnnotationGUI) -> None:
    for item_id in gui.femoral_axis_item_ids:
        try:
            gui.canvas.delete(item_id)
        except Exception as e:
            logger.warning(f"Failed to delete femoral axis item: {e}")
    gui.femoral_axis_item_ids = []


def change_femoral_axis_whisker_tip_length(gui: AnnotationGUI, delta: int) -> None:
    new_len = max(
        1,
        min(80, int(gui.femoral_axis_whisker_tip_length.get()) + delta),
    )
    if new_len != gui.femoral_axis_whisker_tip_length.get():
        gui.femoral_axis_whisker_tip_length.set(new_len)
        update_femoral_axis_overlay(gui)


def get_active_femoral_axis_line_screen(
    gui: AnnotationGUI,
) -> tuple[float, float, float, float] | None:
    if not gui.current_image:
        return None
    if not gui.femoral_axis_enabled.get():
        return None

    landmark = gui.selected_landmark.get()
    if landmark not in ("L-FA", "R-FA"):
        return None

    points = gui._get_line_points(landmark)
    if len(points) >= 2:
        x1, y1 = gui._img_to_screen(*points[0])
        x2, y2 = gui._img_to_screen(*points[1])
        return x1, y1, x2, y2

    if len(points) == 1 and gui.last_mouse_canvas_pos is not None:
        mouse_x, mouse_y = gui.last_mouse_canvas_pos
        x0, y0, x1, y1 = gui._display_rect()
        if x0 <= mouse_x < x1 and y0 <= mouse_y < y1:
            sx, sy = gui._img_to_screen(*points[0])
            return sx, sy, mouse_x, mouse_y

    return None


def update_femoral_axis_overlay(gui: AnnotationGUI) -> None:
    clear_femoral_axis_overlay(gui)

    line = gui._get_active_femoral_axis_line_screen()
    if line is None:
        return

    x1, y1, x2, y2 = line
    vx = float(x2 - x1)
    vy = float(y2 - y1)
    mag = math.hypot(vx, vy)
    if mag < 1e-6:
        return

    tx = float(vx / mag)
    ty = float(vy / mag)
    nx = float(-ty)
    ny = float(tx)

    n_proj = max(1, int(gui.femoral_axis_count.get()))
    proj_len = float(gui.femoral_axis_proj_length.get())
    cap_half = float(gui.femoral_axis_whisker_tip_length.get())

    for i in range(1, n_proj + 1):
        frac = float(i / (n_proj + 1.0))
        cx = float(x1 + frac * vx)
        cy = float(y1 + frac * vy)

        ax = float(cx - proj_len * nx)
        ay = float(cy - proj_len * ny)
        bx = float(cx + proj_len * nx)
        by = float(cy + proj_len * ny)

        main_id = gui.canvas.create_line(
            ax,
            ay,
            bx,
            by,
            fill="magenta",
            width=2,
            tags="femoral_axis",
        )
        cap1_id = gui.canvas.create_line(
            ax - cap_half * tx,
            ay - cap_half * ty,
            ax + cap_half * tx,
            ay + cap_half * ty,
            fill="magenta",
            width=2,
            tags="femoral_axis",
        )
        cap2_id = gui.canvas.create_line(
            bx - cap_half * tx,
            by - cap_half * ty,
            bx + cap_half * tx,
            by + cap_half * ty,
            fill="magenta",
            width=2,
            tags="femoral_axis",
        )
        gui.femoral_axis_item_ids.extend([main_id, cap1_id, cap2_id])

    for item_id in gui.femoral_axis_item_ids:
        try:
            gui.canvas.tag_raise(item_id)
        except Exception:
            pass
    gui.canvas.tag_raise("marker")
