"""Canvas rendering — points, overlays, crosshairs, hover circle."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportPrivateUsage=false, reportUnusedCallResult=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnusedVariable=false, reportUnnecessaryComparison=false, reportUnusedImport=false

import logging
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image, ImageTk

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)

AnnotationPoint = tuple[float, float]
AnnotationValue = AnnotationPoint | list[AnnotationPoint]


def draw_points(gui: AnnotationGUI) -> None:
    gui.canvas.delete("marker")
    if not gui.current_image_path:
        gui._clear_line_preview()
        gui._clear_femoral_axis_overlay()
        return

    pts, _quality = gui._get_annotations()
    gui._update_found_checks(pts)
    current_image_verified = gui._is_current_image_verified()
    x_curr, y_curr = gui._img_to_screen(0, 0)
    label_font = gui.landmark_font.copy()
    label_font.configure(size=30)

    selected_lm = gui.selected_landmark.get()
    if gui._is_line_landmark(selected_lm):
        landmark_is_labeled = len(gui._get_line_points(selected_lm)) > 0
    else:
        landmark_is_labeled = selected_lm in pts.keys()

    if selected_lm:
        gui.canvas.create_text(
            x_curr,
            y_curr,
            text=selected_lm,
            fill=("#FFCC66" if landmark_is_labeled else "#FF8066"),
            font=label_font,
            tags="marker",
            anchor="nw",
        )

    key = (
        gui._path_key(gui.current_image_path)
        if gui.json_path is not None
        else str(gui.current_image_path)
    )
    meta = gui.landmark_meta.get(key, {})

    for lm, val in pts.items():
        vis_var = gui.landmark_visibility.get(lm)
        if vis_var is not None and not vis_var.get():
            continue

        drawing_current_selected = lm == gui.selected_landmark.get()
        is_flagged = bool(meta.get(lm, {}).get("flag", False))
        oval_color = (
            "blue"
            if drawing_current_selected
            else ("red" if not current_image_verified else "green")
        )
        text_color = (
            "orange"
            if drawing_current_selected
            else ("red" if is_flagged else "yellow")
        )
        font = gui.landmark_font if drawing_current_selected else gui.dialogue_font
        shadow_font = font.copy()
        shadow_font.configure(size=font.cget("size") + 1)

        if gui._is_line_landmark(lm):
            line_pts = gui._get_line_points(lm)
            if not line_pts:
                continue

            screen_pts = [gui._img_to_screen(x, y) for x, y in line_pts]

            line_color = "blue" if drawing_current_selected else "red"
            if len(screen_pts) == 2:
                xs1, ys1 = screen_pts[0]
                xs2, ys2 = screen_pts[1]
                gui.canvas.create_line(
                    xs1,
                    ys1,
                    xs2,
                    ys2,
                    fill=line_color,
                    width=2,
                    tags="marker",
                )
                label_x = (xs1 + xs2) / 2
                label_y = (ys1 + ys2) / 2 - 14
            else:
                label_x, label_y = screen_pts[0][0], screen_pts[0][1] - 14

            for xs, ys in screen_pts:
                r = 5
                gui.canvas.create_oval(
                    xs - r,
                    ys - r,
                    xs + r,
                    ys + r,
                    outline=line_color,
                    width=2,
                    tags="marker",
                )

            gui.canvas.create_text(
                label_x - 1,
                label_y - 1,
                text=lm,
                fill="black",
                font=shadow_font,
                tags="marker",
            )
            gui.canvas.create_text(
                label_x,
                label_y,
                text=lm,
                fill=text_color,
                font=font,
                tags="marker",
            )
            continue

        if not (
            isinstance(val, tuple)
            and len(val) == 2
            and all(isinstance(v, (int, float)) for v in val)
        ):
            continue

        x, y = val
        y_offset_label = 16 if drawing_current_selected else 12
        xs, ys = gui._img_to_screen(x, y)

        r = 5
        gui.canvas.create_oval(
            xs - r,
            ys - r,
            xs + r,
            ys + r,
            outline=oval_color,
            width=2,
            tags="marker",
        )
        if gui.check_csv_mode and drawing_current_selected:
            gui.canvas.create_oval(
                xs - 10 * r,
                ys - 10 * r,
                xs + 10 * r,
                ys + 10 * r,
                outline=oval_color,
                width=6,
                tags="marker",
            )

        gui.canvas.create_text(
            xs - 1,
            ys - y_offset_label - 1,
            text=lm,
            fill="black",
            font=shadow_font,
            tags="marker",
        )
        gui.canvas.create_text(
            xs,
            ys - y_offset_label,
            text=lm,
            fill=text_color,
            font=font,
            tags="marker",
        )

    for lm in ("LOB", "ROB"):
        update_overlay_for(gui, lm)
    update_pair_lines(gui)
    gui._update_femoral_axis_overlay()


def _remove_pair_lines(gui: AnnotationGUI) -> None:
    for key, line_id in list(gui.pair_line_ids.items()):
        try:
            gui.canvas.delete(line_id)
        except Exception as e:
            logger.warning(f"Failed to delete pair line {key}: {e}")
        gui.pair_line_ids.pop(key, None)


def _find_landmark_key(gui: AnnotationGUI, name_lower: str) -> str | None:
    for k in gui.landmarks:
        if k.lower() == name_lower:
            return k
    return None


def update_pair_lines(gui: AnnotationGUI) -> None:
    if not gui.current_image_path:
        _remove_pair_lines(gui)
        return

    pts, _quality = gui._get_annotations()
    pairs = [("ldf", "lpf"), ("rdf", "rpf")]
    color = "#00FFFF"
    for a, b in pairs:
        key = f"{a}_{b}"
        ka = _find_landmark_key(gui, a)
        kb = _find_landmark_key(gui, b)
        if ka is None or kb is None:
            return
        if ka in pts and kb in pts:
            va = gui.landmark_visibility.get(ka)
            vb = gui.landmark_visibility.get(kb)
            if (va is None or va.get()) and (vb is None or vb.get()):
                point_a = pts[ka]
                point_b = pts[kb]
                if not (
                    isinstance(point_a, tuple)
                    and len(point_a) == 2
                    and all(isinstance(v, (int, float)) for v in point_a)
                    and isinstance(point_b, tuple)
                    and len(point_b) == 2
                    and all(isinstance(v, (int, float)) for v in point_b)
                ):
                    continue
                x1, y1 = point_a
                x2, y2 = point_b
                xs1, ys1 = gui._img_to_screen(x1, y1)
                xs2, ys2 = gui._img_to_screen(x2, y2)
                if key in gui.pair_line_ids:
                    gui.canvas.coords(gui.pair_line_ids[key], xs1, ys1, xs2, ys2)
                else:
                    gui.pair_line_ids[key] = gui.canvas.create_line(
                        xs1, ys1, xs2, ys2, fill=color, width=2, tags="pairline"
                    )
                try:
                    gui.canvas.tag_lower(gui.pair_line_ids[key], "marker")
                except Exception as e:
                    logger.warning(f"Failed to lower pair line {key}: {e}")
                continue
        if key in gui.pair_line_ids:
            try:
                gui.canvas.delete(gui.pair_line_ids[key])
            except Exception as e:
                logger.warning(f"Failed to delete pair line {key}: {e}")
            gui.pair_line_ids.pop(key, None)


def toggle_extended_crosshair(gui: AnnotationGUI) -> None:
    enabled = gui.extended_crosshair_enabled.get()
    gui.crosshair_length_scale.config(state="normal" if enabled else "disabled")

    if not enabled:
        hide_extended_crosshair(gui)
        gui._hide_zoom_extended_crosshair()
    else:
        if gui.last_mouse_canvas_pos is not None:
            x, y = gui.last_mouse_canvas_pos
            update_extended_crosshair(gui, x, y)
        gui._update_zoom_extended_crosshair()


def on_extended_crosshair_length_change(gui: AnnotationGUI, _value: str) -> None:
    if not gui.extended_crosshair_enabled.get():
        return

    length = max(5, min(400, gui.extended_crosshair_length.get()))
    gui.extended_crosshair_length.set(length)

    if gui.last_mouse_canvas_pos is not None:
        x, y = gui.last_mouse_canvas_pos
        update_extended_crosshair(gui, x, y)

    gui._update_zoom_extended_crosshair()


def update_extended_crosshair(gui: AnnotationGUI, x: float, y: float) -> None:
    length = gui.extended_crosshair_length.get()

    if not gui.extended_crosshair_ids:
        hline_id = gui.canvas.create_line(
            x - length,
            y,
            x + length,
            y,
            fill="lime",
            width=1,
            tags="extended_crosshair",
        )
        vline_id = gui.canvas.create_line(
            x,
            y - length,
            x,
            y + length,
            fill="lime",
            width=1,
            tags="extended_crosshair",
        )
        gui.extended_crosshair_ids = [hline_id, vline_id]
    else:
        hline_id, vline_id = gui.extended_crosshair_ids
        gui.canvas.coords(hline_id, x - length, y, x + length, y)
        gui.canvas.coords(vline_id, x, y - length, x, y + length)

    for item_id in gui.extended_crosshair_ids:
        gui.canvas.tag_raise(item_id)


def hide_extended_crosshair(gui: AnnotationGUI) -> None:
    for item_id in gui.extended_crosshair_ids:
        try:
            gui.canvas.delete(item_id)
        except Exception as e:
            logger.warning(f"Failed to delete extended crosshair item: {e}")
    gui.extended_crosshair_ids = []


def toggle_hover(gui: AnnotationGUI) -> None:
    enabled = gui.hover_enabled.get()
    gui.radius_scale.config(state="normal" if enabled else "disabled")
    if enabled and gui.femoral_axis_enabled.get():
        gui.femoral_axis_enabled.set(False)
        gui.femoral_axis_count_scale.config(state="disabled")
        gui.femoral_axis_whisker_tip_length_scale.config(state="disabled")
        gui._clear_femoral_axis_overlay()
    if not enabled:
        hide_hover_circle(gui)


def on_radius_change(gui: AnnotationGUI, _value: str) -> None:
    if not gui.hover_enabled.get():
        return
    r = max(1, min(300, gui.hover_radius.get()))
    gui.hover_radius.set(r)
    if gui.hover_circle_id is not None:
        x0, y0, x1, y1 = gui.canvas.coords(gui.hover_circle_id)
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        update_hover_circle(gui, cx, cy)


def update_hover_circle(gui: AnnotationGUI, x: float, y: float) -> None:
    r = gui.hover_radius.get()
    x0, y0, x1, y1 = x - r, y - r, x + r, y + r
    if gui.hover_circle_id is None:
        gui.hover_circle_id = gui.canvas.create_oval(
            x0, y0, x1, y1, outline="cyan", width=1, tags="hover_circle"
        )
    else:
        gui.canvas.coords(gui.hover_circle_id, x0, y0, x1, y1)


def update_mouse_crosshair(gui: AnnotationGUI, x: float, y: float) -> None:
    circle_r = 8
    cross_r = 4

    if not gui.mouse_crosshair_ids:
        circle_id = gui.canvas.create_oval(
            x - circle_r,
            y - circle_r,
            x + circle_r,
            y + circle_r,
            outline="cyan",
            width=1,
            tags="mouse_crosshair",
        )
        hline_id = gui.canvas.create_line(
            x - cross_r,
            y,
            x + cross_r,
            y,
            fill="cyan",
            width=1,
            tags="mouse_crosshair",
        )
        vline_id = gui.canvas.create_line(
            x,
            y - cross_r,
            x,
            y + cross_r,
            fill="cyan",
            width=1,
            tags="mouse_crosshair",
        )
        gui.mouse_crosshair_ids = [circle_id, hline_id, vline_id]
    else:
        circle_id, hline_id, vline_id = gui.mouse_crosshair_ids
        gui.canvas.coords(
            circle_id,
            x - circle_r,
            y - circle_r,
            x + circle_r,
            y + circle_r,
        )
        gui.canvas.coords(hline_id, x - cross_r, y, x + cross_r, y)
        gui.canvas.coords(vline_id, x, y - cross_r, x, y + cross_r)

    for item_id in gui.mouse_crosshair_ids:
        gui.canvas.tag_raise(item_id)


def hide_mouse_crosshair(gui: AnnotationGUI) -> None:
    for item_id in gui.mouse_crosshair_ids:
        gui.canvas.delete(item_id)
    gui.mouse_crosshair_ids = []


def hide_hover_circle(gui: AnnotationGUI) -> None:
    if gui.hover_circle_id is not None:
        gui.canvas.delete(gui.hover_circle_id)
        gui.hover_circle_id = None


def remove_all_overlays(gui: AnnotationGUI) -> None:
    for lm in list(gui.seg_item_ids.keys()):
        try:
            gui.canvas.delete(gui.seg_item_ids[lm])
        except Exception as e:
            logger.warning(f"Failed to delete overlay for {lm}: {e}")
    gui.seg_item_ids.clear()
    gui.seg_img_objs.clear()
    _remove_pair_lines(gui)


def remove_overlay_for(gui: AnnotationGUI, lm: str) -> None:
    if lm in gui.seg_item_ids:
        try:
            gui.canvas.delete(gui.seg_item_ids[lm])
        except Exception as e:
            logger.warning(f"Failed to delete overlay for {lm}: {e}")
        gui.seg_item_ids.pop(lm, None)
        gui.seg_img_objs.pop(lm, None)


def update_overlay_for(gui: AnnotationGUI, lm: str) -> None:
    vis = True
    vis_var = gui.landmark_visibility.get(lm)
    if vis_var is not None:
        vis = bool(vis_var.get())
    has_mask = (
        gui.current_image_path
        and str(gui.current_image_path) in gui.seg_masks
        and lm in gui.seg_masks[str(gui.current_image_path)]
    )
    if not has_mask or not vis:
        remove_overlay_for(gui, lm)
        return
    _mask = gui.seg_masks[str(gui.current_image_path)][lm]
    # render_overlay_for(gui, lm, _mask)
    gui.canvas.tag_raise("marker")


def render_overlay_for(
    gui: AnnotationGUI,
    lm: str,
    mask: np.ndarray,
    fill_rgba: tuple[int, int, int, int] = (0, 255, 255, 120),
) -> None:
    if mask is None or gui.current_image is None:
        return

    if gui.disp_size == (0, 0):
        gui._recompute_transform()

    disp_w, disp_h = gui.disp_size
    off_x, off_y = gui.disp_off

    mask_u8 = (mask > 0).astype(np.uint8) * 255
    mask_img = Image.fromarray(mask_u8, mode="L").resize(
        (disp_w, disp_h), Image.Resampling.NEAREST
    )

    overlay = Image.new("RGBA", (disp_w, disp_h), (0, 0, 0, 0))
    color_img = Image.new("RGBA", (disp_w, disp_h), fill_rgba)

    overlay.paste(color_img, (0, 0), mask_img)

    gui.seg_img_objs[lm] = ImageTk.PhotoImage(overlay)

    if lm not in gui.seg_item_ids:
        gui.seg_item_ids[lm] = gui.canvas.create_image(
            off_x,
            off_y,
            anchor="nw",
            image=gui.seg_img_objs[lm],
            tags=f"seg_{lm}",
        )
    else:
        gui.canvas.itemconfigure(gui.seg_item_ids[lm], image=gui.seg_img_objs[lm])
        gui.canvas.coords(gui.seg_item_ids[lm], off_x, off_y)

    gui.canvas.tag_lower(gui.seg_item_ids[lm], "marker")
    gui.canvas.tag_raise("marker")


def clear_line_preview(gui: AnnotationGUI) -> None:
    canvas = getattr(gui, "canvas")
    if gui.line_preview_id is not None:
        try:
            canvas.delete(gui.line_preview_id)
        except Exception as e:
            logger.warning(f"Failed to delete line preview: {e}")
        gui.line_preview_id = None


def update_line_preview(gui: AnnotationGUI, x: float, y: float) -> None:
    canvas = getattr(gui, "canvas")
    lm = gui.selected_landmark.get()
    if not lm or not gui._is_line_landmark(lm):
        clear_line_preview(gui)
        return

    pts = gui._get_line_points(lm)
    if len(pts) != 1:
        clear_line_preview(gui)
        return

    x0, y0 = gui._img_to_screen(*pts[0])

    if gui.line_preview_id is None:
        gui.line_preview_id = canvas.create_line(
            x0,
            y0,
            x,
            y,
            fill="cyan",
            width=2,
            dash=(4, 2),
            tags="line_preview",
        )
    else:
        canvas.coords(gui.line_preview_id, x0, y0, x, y)

    try:
        canvas.tag_lower(gui.line_preview_id, "marker")
    except Exception:
        pass


def render_base_image(gui: AnnotationGUI) -> None:
    canvas = getattr(gui, "canvas")
    if not gui.current_image:
        return

    gui._recompute_transform()
    disp_w, disp_h = gui.disp_size
    off_x, off_y = gui.disp_off

    resized = gui.current_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
    gui.img_obj = ImageTk.PhotoImage(resized)

    if gui.base_img_item is None:
        gui.base_img_item = canvas.create_image(
            off_x, off_y, anchor="nw", image=gui.img_obj, tags="base"
        )
    else:
        canvas.itemconfigure(gui.base_img_item, image=gui.img_obj)
        canvas.coords(gui.base_img_item, off_x, off_y)


def remove_pair_lines(gui: AnnotationGUI) -> None:
    _remove_pair_lines(gui)


def find_landmark_key(gui: AnnotationGUI, lm: str) -> str | None:
    return _find_landmark_key(gui, lm)


def set_selected_visibility(gui: AnnotationGUI, visible: bool) -> None:
    lm = gui.selected_landmark.get()
    if not lm:
        return
    var = gui.landmark_visibility.get(lm)
    if var is None:
        return
    var.set(visible)
    gui._draw_points()
