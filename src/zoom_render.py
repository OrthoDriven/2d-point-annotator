"""Zoom view rendering — extracted from AnnotationGUI."""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PIL import Image, ImageTk

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)


def get_zoom_canvas_size(gui: AnnotationGUI) -> int:
    if gui.zoom_canvas is None:
        return 1

    w = gui.zoom_canvas.winfo_width()
    h = gui.zoom_canvas.winfo_height()

    if w <= 1 or h <= 1:
        req_w = gui.zoom_canvas.winfo_reqwidth()
        req_h = gui.zoom_canvas.winfo_reqheight()
        w = max(w, req_w, 1)
        h = max(h, req_h, 1)

    return max(1, min(w, h))


def render_black_zoom_view(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    size = get_zoom_canvas_size(gui)
    black_img = Image.new("RGB", (size, size), "black")
    gui.zoom_img_obj = ImageTk.PhotoImage(black_img)

    if gui.zoom_base_item is None:
        gui.zoom_base_item = gui.zoom_canvas.create_image(
            0, 0, anchor="nw", image=gui.zoom_img_obj
        )
    else:
        _ = gui.zoom_canvas.itemconfigure(gui.zoom_base_item, image=gui.zoom_img_obj)
        gui.zoom_canvas.coords(gui.zoom_base_item, 0, 0)

    gui.zoom_src_rect = None
    update_zoom_crosshair(gui)
    clear_zoom_landmark_overlay(gui)


def update_zoom_view(
    gui: AnnotationGUI, mouse_x: float | None = None, mouse_y: float | None = None
) -> None:
    if gui.zoom_canvas is None:
        return

    size = get_zoom_canvas_size(gui)

    if gui.current_image is None or mouse_x is None or mouse_y is None:
        render_black_zoom_view(gui)
        return

    x0, y0, x1, y1 = gui._display_rect()
    if not (x0 <= mouse_x < x1 and y0 <= mouse_y < y1):
        render_black_zoom_view(gui)
        return

    xi, yi = gui._screen_to_img(mouse_x, mouse_y)
    iw, ih = gui.current_image.size

    if not (0 <= xi < iw and 0 <= yi < ih):
        render_black_zoom_view(gui)
        return

    zoom_lev = max(2, min(40, float(gui.zoom_percent.get())))
    half_w = max(1.0, iw / (zoom_lev * 2.0))
    half_h = max(1.0, ih / (zoom_lev * 2.0))

    src_left = float(xi) - half_w
    src_top = float(yi) - half_h
    src_right = float(xi) + half_w
    src_bottom = float(yi) + half_h

    gui.zoom_src_rect = (src_left, src_top, src_right, src_bottom)

    try:
        out = gui.current_image.transform(
            (size, size),
            Image.Transform.EXTENT,
            gui.zoom_src_rect,
            resample=Image.Resampling.BICUBIC,
            fill=0,
        )
    except TypeError:
        out = gui.current_image.transform(
            (size, size),
            Image.Transform.EXTENT,
            gui.zoom_src_rect,
            resample=Image.Resampling.BICUBIC,
        )

    gui.zoom_img_obj = ImageTk.PhotoImage(out)

    if gui.zoom_base_item is None:
        gui.zoom_base_item = gui.zoom_canvas.create_image(
            0, 0, anchor="nw", image=gui.zoom_img_obj
        )
    else:
        _ = gui.zoom_canvas.itemconfigure(gui.zoom_base_item, image=gui.zoom_img_obj)
        gui.zoom_canvas.coords(gui.zoom_base_item, 0, 0)

    update_zoom_crosshair(gui)
    refresh_zoom_landmark_overlay(gui)


def on_zoom_change(gui: AnnotationGUI, _value: str) -> None:
    if gui.last_mouse_canvas_pos is None:
        update_zoom_view(gui, None, None)
        return

    mouse_x, mouse_y = gui.last_mouse_canvas_pos
    update_zoom_view(gui, mouse_x, mouse_y)


def change_zoom_percent(gui: AnnotationGUI, delta: int) -> None:
    new_zoom = max(2, min(40, gui.zoom_percent.get() + delta))
    if new_zoom != gui.zoom_percent.get():
        gui.zoom_percent.set(new_zoom)
        on_zoom_change(gui, str(new_zoom))


def update_zoom_crosshair(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    size = get_zoom_canvas_size(gui)
    x = size / 2
    y = size / 2

    circle_r = 16
    cross_r = circle_r

    circle_color = "blue"
    crosshair_color = "orange"

    if not gui.zoom_crosshair_ids:
        circle_id = gui.zoom_canvas.create_oval(
            x - circle_r,
            y - circle_r,
            x + circle_r,
            y + circle_r,
            outline=circle_color,
            width=1,
            tags="zoom_crosshair",
        )
        hline_id = gui.zoom_canvas.create_line(
            x - cross_r,
            y,
            x + cross_r,
            y,
            fill=crosshair_color,
            width=1,
            tags="zoom_crosshair",
        )
        vline_id = gui.zoom_canvas.create_line(
            x,
            y - cross_r,
            x,
            y + cross_r,
            fill=crosshair_color,
            width=1,
            tags="zoom_crosshair",
        )
        gui.zoom_crosshair_ids = [circle_id, hline_id, vline_id]
    else:
        circle_id, hline_id, vline_id = gui.zoom_crosshair_ids
        gui.zoom_canvas.coords(
            circle_id,
            x - circle_r,
            y - circle_r,
            x + circle_r,
            y + circle_r,
        )
        gui.zoom_canvas.coords(hline_id, x - cross_r, y, x + cross_r, y)
        gui.zoom_canvas.coords(vline_id, x, y - cross_r, x, y + cross_r)
        _ = gui.zoom_canvas.itemconfigure(circle_id, outline=circle_color)
        _ = gui.zoom_canvas.itemconfigure(hline_id, fill=crosshair_color)
        _ = gui.zoom_canvas.itemconfigure(vline_id, fill=crosshair_color)

    for item_id in gui.zoom_crosshair_ids:
        gui.zoom_canvas.tag_raise(item_id)

    update_zoom_extended_crosshair(gui)


def hide_zoom_crosshair(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    for item_id in gui.zoom_crosshair_ids:
        gui.zoom_canvas.delete(item_id)
    gui.zoom_crosshair_ids = []


def update_zoom_extended_crosshair(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    if not gui.extended_crosshair_enabled.get():
        hide_zoom_extended_crosshair(gui)
        return

    size = get_zoom_canvas_size(gui)
    x = size / 2
    y = size / 2

    length = max(5, min(400, int(gui.extended_crosshair_length.get())))

    # Keep it inside the zoom canvas
    max_len = max(1, int(size / 2) - 2)
    length = min(length, max_len)

    if not gui.zoom_extended_crosshair_ids:
        hline_id = gui.zoom_canvas.create_line(
            x - length,
            y,
            x + length,
            y,
            fill="lime",
            width=1,
            tags="zoom_extended_crosshair",
        )
        vline_id = gui.zoom_canvas.create_line(
            x,
            y - length,
            x,
            y + length,
            fill="lime",
            width=1,
            tags="zoom_extended_crosshair",
        )
        gui.zoom_extended_crosshair_ids = [hline_id, vline_id]
    else:
        hline_id, vline_id = gui.zoom_extended_crosshair_ids
        gui.zoom_canvas.coords(hline_id, x - length, y, x + length, y)
        gui.zoom_canvas.coords(vline_id, x, y - length, x, y + length)

    for item_id in gui.zoom_extended_crosshair_ids:
        gui.zoom_canvas.tag_raise(item_id)


def hide_zoom_extended_crosshair(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    for item_id in gui.zoom_extended_crosshair_ids:
        try:
            gui.zoom_canvas.delete(item_id)
        except Exception as e:
            logger.warning(f"Failed to delete zoom extended crosshair item: {e}")
    gui.zoom_extended_crosshair_ids = []


def refresh_zoom_landmark_overlay(gui: AnnotationGUI) -> None:
    clear_zoom_landmark_overlay(gui)

    if gui.zoom_canvas is None:
        return
    if not gui.show_selected_landmark_in_zoom.get():
        return
    if gui.current_image is None or gui.current_image_path is None:
        return
    if gui.zoom_src_rect is None:
        return

    lm = gui.selected_landmark.get().strip()
    if not lm:
        return

    pts, _quality = gui._get_annotations()
    size = get_zoom_canvas_size(gui)
    if size <= 1:
        return

    src_left, src_top, src_right, src_bottom = gui.zoom_src_rect
    src_w = src_right - src_left
    src_h = src_bottom - src_top
    if abs(src_w) < 1e-12 or abs(src_h) < 1e-12:
        return

    def img_to_zoom(px: float, py: float) -> tuple[float, float]:
        zx = ((float(px) - src_left) / src_w) * size
        zy = ((float(py) - src_top) / src_h) * size
        return zx, zy

    overlay_ids: list[int] = []

    if gui._is_line_landmark(lm):
        line_pts = gui._get_line_points(lm)
        if not line_pts:
            return

        zoom_pts = [img_to_zoom(px, py) for px, py in line_pts]
        if len(zoom_pts) == 2:
            line_id = gui.zoom_canvas.create_line(
                zoom_pts[0][0],
                zoom_pts[0][1],
                zoom_pts[1][0],
                zoom_pts[1][1],
                fill="cyan",
                width=2,
                tags="zoom_landmark_overlay",
            )
            overlay_ids.append(line_id)

        r = 7
        for zx, zy in zoom_pts:
            circle_id = gui.zoom_canvas.create_oval(
                zx - r,
                zy - r,
                zx + r,
                zy + r,
                outline="cyan",
                width=2,
                tags="zoom_landmark_overlay",
            )
            hline_id = gui.zoom_canvas.create_line(
                zx - r,
                zy,
                zx + r,
                zy,
                fill="cyan",
                width=1,
                tags="zoom_landmark_overlay",
            )
            vline_id = gui.zoom_canvas.create_line(
                zx,
                zy - r,
                zx,
                zy + r,
                fill="cyan",
                width=1,
                tags="zoom_landmark_overlay",
            )
            overlay_ids.extend([circle_id, hline_id, vline_id])
    else:
        if lm not in pts:
            return

        px, py = pts[lm]
        if not (isinstance(px, (int, float)) and isinstance(py, (int, float))):
            return

        zx, zy = img_to_zoom(px, py)

        r = 7
        circle_id = gui.zoom_canvas.create_oval(
            zx - r,
            zy - r,
            zx + r,
            zy + r,
            outline="cyan",
            width=2,
            tags="zoom_landmark_overlay",
        )
        hline_id = gui.zoom_canvas.create_line(
            zx - r,
            zy,
            zx + r,
            zy,
            fill="cyan",
            width=1,
            tags="zoom_landmark_overlay",
        )
        vline_id = gui.zoom_canvas.create_line(
            zx,
            zy - r,
            zx,
            zy + r,
            fill="cyan",
            width=1,
            tags="zoom_landmark_overlay",
        )
        overlay_ids.extend([circle_id, hline_id, vline_id])

    gui.zoom_landmark_overlay_ids = overlay_ids

    for item_id in gui.zoom_landmark_overlay_ids:
        try:
            gui.zoom_canvas.tag_raise(item_id)
        except Exception:
            pass

    for item_id in gui.zoom_crosshair_ids:
        try:
            gui.zoom_canvas.tag_raise(item_id)
        except Exception:
            pass

    for item_id in gui.zoom_extended_crosshair_ids:
        try:
            gui.zoom_canvas.tag_raise(item_id)
        except Exception:
            pass


def clear_zoom_landmark_overlay(gui: AnnotationGUI) -> None:
    if gui.zoom_canvas is None:
        return

    for item_id in gui.zoom_landmark_overlay_ids:
        try:
            gui.zoom_canvas.delete(item_id)
        except Exception as e:
            logger.warning(f"Failed to delete zoom landmark overlay item: {e}")
    gui.zoom_landmark_overlay_ids = []
