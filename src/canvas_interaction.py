"""Canvas mouse/keyboard interaction — click, drag, scroll handlers."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportUnknownVariableType=false

import logging
from tkinter import messagebox
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)


def on_canvas_resize(gui: AnnotationGUI, _event=None) -> None:
    if not gui.current_image:
        gui._clear_line_preview()
        gui._update_zoom_view(None, None)
        gui._clear_femoral_axis_overlay()
        gui._hide_extended_crosshair()
        gui._hide_zoom_extended_crosshair()
        return
    gui._render_base_image()
    gui._draw_points()
    for lm in ("LOB", "ROB"):
        gui._update_overlay_for(lm)
    if gui.last_mouse_canvas_pos is None:
        gui._clear_line_preview()
        gui._update_zoom_view(None, None)
        gui._update_femoral_axis_overlay()
        gui._hide_extended_crosshair()
        gui._hide_zoom_extended_crosshair()
        return

    mouse_x, mouse_y = gui.last_mouse_canvas_pos
    x0, y0, x1, y1 = gui._display_rect()
    if x0 <= mouse_x < x1 and y0 <= mouse_y < y1:
        gui._update_zoom_view(mouse_x, mouse_y)
        gui._update_line_preview(mouse_x, mouse_y)
        gui._update_femoral_axis_overlay()
        if gui.extended_crosshair_enabled.get():
            gui._update_extended_crosshair(mouse_x, mouse_y)
        else:
            gui._hide_extended_crosshair()
    else:
        gui._clear_line_preview()
        gui._update_zoom_view(None, None)
        gui._clear_femoral_axis_overlay()
        gui._hide_extended_crosshair()
        gui._hide_zoom_extended_crosshair()


def on_mouse_move(gui: AnnotationGUI, event) -> None:
    if not gui.current_image:
        gui.last_mouse_canvas_pos = None
        gui._clear_line_preview()
        gui._clear_femoral_axis_overlay()
        gui._hide_mouse_crosshair()
        gui._update_zoom_view(None, None)
        gui._hide_extended_crosshair()
        gui._hide_zoom_extended_crosshair()
        return
    x0, y0, x1, y1 = gui._display_rect()
    if x0 <= event.x < x1 and y0 <= event.y < y1:
        gui.last_mouse_canvas_pos = (event.x, event.y)
        gui._update_mouse_crosshair(event.x, event.y)
        gui._update_zoom_view(event.x, event.y)
        gui._update_line_preview(event.x, event.y)
        gui._update_femoral_axis_overlay()
        if gui.hover_enabled.get():
            gui._update_hover_circle(
                event.x, event.y
            )  # hover circle stays screen-space
        else:
            gui._hide_hover_circle()
        if gui.extended_crosshair_enabled.get():
            gui._update_extended_crosshair(event.x, event.y)
        else:
            gui._hide_extended_crosshair()
    else:
        gui.last_mouse_canvas_pos = None
        gui._clear_line_preview()
        gui._clear_femoral_axis_overlay()
        gui._hide_mouse_crosshair()
        gui._hide_hover_circle()
        gui._update_zoom_view(None, None)
        gui._hide_extended_crosshair()
        gui._hide_zoom_extended_crosshair()


def on_canvas_leave(gui: AnnotationGUI, _event) -> None:
    gui._hide_hover_circle()
    gui._clear_femoral_axis_overlay()
    gui._hide_extended_crosshair()
    gui._hide_mouse_crosshair()
    gui._clear_line_preview()
    gui.last_mouse_canvas_pos = None
    gui._update_zoom_view(None, None)
    gui._hide_zoom_extended_crosshair()


def on_mousewheel(gui: AnnotationGUI, event) -> None:
    if gui.right_mouse_held:
        step = 2 if event.delta > 0 else -2
        gui._change_zoom_percent(step)
        return
    if gui.femoral_axis_enabled.get() and gui.selected_landmark.get() in (
        "L-FA",
        "R-FA",
    ):
        step = 2 if event.delta > 0 else -2
        gui._change_femoral_axis_length(step)
        return
    if not gui.hover_enabled.get():
        return
    step = 2 if event.delta > 0 else -2
    gui._change_radius(step)


def on_scroll_linux(gui: AnnotationGUI, direction: int) -> None:
    if gui.right_mouse_held:
        step = 2 if direction > 0 else -2
        gui._change_zoom_percent(step)
        return
    if gui.femoral_axis_enabled.get() and gui.selected_landmark.get() in (
        "L-FA",
        "R-FA",
    ):
        step = 2 if direction > 0 else -2
        gui._change_femoral_axis_length(step)
        return
    if not gui.hover_enabled.get():
        return
    step = 2 if direction > 0 else -2
    gui._change_radius(step)


def on_right_button_press(gui: AnnotationGUI, event) -> None:
    _ = event
    gui.right_mouse_held = True


def on_right_button_release(gui: AnnotationGUI, event) -> None:
    _ = event
    gui.right_mouse_held = False


def on_left_press(gui: AnnotationGUI, event) -> None:
    x0, y0, x1, y1 = gui._display_rect()
    if not gui.current_image:
        return
    if not (x0 <= event.x < x1 and y0 <= event.y < y1):
        return

    gui.last_mouse_canvas_pos = (event.x, event.y)
    gui._update_mouse_crosshair(event.x, event.y)
    gui._update_zoom_view(event.x, event.y)

    lm = gui.selected_landmark.get()
    if not lm:
        messagebox.showwarning("No Landmark", "Please select a landmark in the list.")
        return

    xi, yi = gui._screen_to_img(event.x, event.y)
    x, y = gui._clamp_img_point(xi, yi)

    if gui._is_line_landmark(lm):
        hit_idx = gui._find_line_point_hit(lm, event.x, event.y)
        if hit_idx is not None:
            gui.dragging_landmark = lm
            gui.dragging_point_index = hit_idx
            gui.dragging_line_whole = False
            gui.dragging_line_last_img_pos = None
            return

        pts = gui._get_line_points(lm)
        if len(pts) == 2 and gui._is_line_hit(lm, event.x, event.y):
            gui.dragging_landmark = lm
            gui.dragging_point_index = None
            gui.dragging_line_whole = True
            gui.dragging_line_last_img_pos = (x, y)
            return

        if len(pts) == 0:
            if not check_left_right_order_for_landmark(gui, lm, x, y):
                return
            gui._set_line_points(lm, [(x, y)])
        elif len(pts) == 1:
            mean_x = (pts[0][0] + x) / 2.0
            if not check_left_right_order_for_landmark(gui, lm, mean_x, y):
                return
            gui._set_line_points(lm, [pts[0], (x, y)])
            gui._clear_line_preview()
        else:
            if not check_left_right_order_for_landmark(gui, lm, x, y):
                return
            gui._set_line_points(lm, [(x, y)])
            gui._clear_line_preview()

        gui._draw_points()
        gui._refresh_zoom_landmark_overlay()
        gui.dirty = True
        gui._auto_save_to_db()
        return

    if not check_left_right_order_for_landmark(gui, lm, x, y):
        return

    gui.annotations.setdefault(str(gui.current_image_path), {})[lm] = (x, y)
    if lm in gui.landmark_found:
        gui.landmark_found[lm].set(True)
    gui._draw_points()
    gui._refresh_zoom_landmark_overlay()
    gui.dirty = True
    if lm in ("LOB", "ROB"):
        if cv2 is None:
            messagebox.showerror(
                "OpenCV missing",
                'cv2 is not available. Install with "pip install opencv-python".',
            )
            return
        gui.last_seed[lm] = (int(x), int(y))
        gui._store_current_settings_for(lm)
        gui._resegment_for(lm)
    gui._auto_save_to_db()
    return


def check_left_right_order_for_landmark(
    gui: AnnotationGUI,
    lm: str,
    new_x: float,
    new_y: float,
) -> bool:
    _ = new_y
    if lm.startswith("L-"):
        other_lm = "R-" + lm[2:]
        is_left_landmark = True
    elif lm.startswith("R-"):
        other_lm = "L-" + lm[2:]
        is_left_landmark = False
    else:
        return True

    allowed = gui._get_allowed_landmarks_for_current_view()
    if other_lm not in allowed:
        return True

    pts, _quality = gui._get_annotations()
    if other_lm not in pts:
        return True

    if gui._is_line_landmark(other_lm):
        other_pts = gui._get_line_points(other_lm)
        if not other_pts:
            return True
        other_x = sum(px for px, _py in other_pts) / len(other_pts)
    else:
        other_pt = pts[other_lm]
        if isinstance(other_pt, tuple):
            other_x = float(other_pt[0])
        else:
            return True

    is_pa = gui.current_image_direction == "PA"

    if is_left_landmark:
        if is_pa:
            is_valid = new_x < other_x
            side_word = "LEFT"
        else:
            is_valid = new_x > other_x
            side_word = "RIGHT"
        bad_msg = (
            f'"{lm}" must be to the {side_word} of "{other_lm}" '
            f"({gui.current_image_direction} image).\n\n"
            f"Current click x = {new_x:.1f}\n"
            f"{other_lm} x = {other_x:.1f}"
        )
    else:
        if is_pa:
            is_valid = new_x > other_x
            side_word = "RIGHT"
        else:
            is_valid = new_x < other_x
            side_word = "LEFT"
        bad_msg = (
            f'"{lm}" must be to the {side_word} of "{other_lm}" '
            f"({gui.current_image_direction} image).\n\n"
            f"Current click x = {new_x:.1f}\n"
            f"{other_lm} x = {other_x:.1f}"
        )

    if not is_valid:
        messagebox.showwarning("Left/Right Landmark Order", bad_msg)
        return False

    return True


def on_left_drag(gui: AnnotationGUI, event) -> None:
    if not gui.current_image:
        return

    gui.last_mouse_canvas_pos = (event.x, event.y)
    gui._update_mouse_crosshair(event.x, event.y)

    if gui.extended_crosshair_enabled.get():
        gui._update_extended_crosshair(event.x, event.y)
    else:
        gui._hide_extended_crosshair()

    gui._update_zoom_view(event.x, event.y)

    if gui.hover_enabled.get():
        gui._update_hover_circle(event.x, event.y)
    else:
        gui._hide_hover_circle()

    x0, y0, x1, y1 = gui._display_rect()
    if not (x0 <= event.x < x1 and y0 <= event.y < y1):
        return

    xi, yi = gui._screen_to_img(event.x, event.y)
    x, y = gui._clamp_img_point(xi, yi)

    if gui.dragging_landmark is None:
        return

    pts = gui._get_line_points(gui.dragging_landmark)
    if not pts:
        return

    if gui.dragging_point_index is not None:
        if gui.dragging_point_index >= len(pts):
            return

        pts[gui.dragging_point_index] = (x, y)
        gui._set_line_points(gui.dragging_landmark, pts)
        gui._draw_points()
        gui._refresh_zoom_landmark_overlay()
        gui.dirty = True
        return

    if gui.dragging_line_whole:
        if len(pts) != 2:
            return

        if gui.dragging_line_last_img_pos is None:
            gui.dragging_line_last_img_pos = (x, y)
            return

        last_x, last_y = gui.dragging_line_last_img_pos
        dx = x - last_x
        dy = y - last_y

        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return

        new_pts = []
        for px, py in pts:
            nx, ny = gui._clamp_img_point(px + dx, py + dy)
            new_pts.append((nx, ny))

        actual_dx = new_pts[0][0] - pts[0][0]
        actual_dy = new_pts[0][1] - pts[0][1]
        new_pts = [
            gui._clamp_img_point(px + actual_dx, py + actual_dy) for px, py in pts
        ]

        gui._set_line_points(gui.dragging_landmark, new_pts)
        gui.dragging_line_last_img_pos = (x, y)
        gui._draw_points()
        gui._refresh_zoom_landmark_overlay()
        gui.dirty = True


def on_left_release(gui: AnnotationGUI, event) -> None:
    x0, y0, x1, y1 = gui._display_rect()
    if gui.current_image and x0 <= event.x < x1 and y0 <= event.y < y1:
        gui.last_mouse_canvas_pos = (event.x, event.y)
        gui._update_mouse_crosshair(event.x, event.y)
        gui._update_zoom_view(event.x, event.y)
        gui._update_line_preview(event.x, event.y)

    if gui.dragging_landmark is not None:
        gui.dragging_landmark = None
        gui.dragging_point_index = None
        gui.dragging_line_whole = False
        gui.dragging_line_last_img_pos = None
        gui._auto_save_to_db()
