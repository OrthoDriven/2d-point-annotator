"""Landmark panel — radio buttons, checkboxes, note editor, visibility."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingTypeArgument=false, reportUninitializedInstanceVariable=false, reportOperatorIssue=false, reportAttributeAccessIssue=false, reportImportCycles=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportImplicitStringConcatenation=false, reportUnnecessaryCast=false

import logging
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, cast

import cv2

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)


def build_landmark_panel(gui: AnnotationGUI) -> None:
    for w in gui.lp_inner.winfo_children():
        w.destroy()
    gui.landmark_visibility.clear()
    gui.landmark_found.clear()
    gui.landmark_flagged.clear()
    gui.landmark_radio_widgets = {}
    gui.landmark_found_widgets = {}
    gui.landmark_flag_widgets = {}

    gui.landmark_table = tk.Frame(gui.lp_inner)
    gui.landmark_table.pack(fill="x", padx=2, pady=2)
    gui.landmark_table.grid_columnconfigure(0, minsize=55)
    gui.landmark_table.grid_columnconfigure(1, minsize=140)
    gui.landmark_table.grid_columnconfigure(2, minsize=80)
    gui.landmark_table.grid_columnconfigure(3, minsize=60)

    key = (
        gui._path_key(gui.current_image_path)
        if gui.json_path is not None and gui.current_image_path is not None
        else str(gui.current_image_path)
    )
    meta = gui.landmark_meta.get(key, {})

    allowed = get_allowed_landmarks_for_current_view(gui)
    visible_landmarks = [lm for lm in gui.landmarks if lm in allowed]

    for i, lm in enumerate(visible_landmarks, start=0):
        vis_var = tk.BooleanVar(value=True)
        found_var = tk.BooleanVar(value=False)
        flag_var = tk.BooleanVar(value=bool(meta.get(lm, {}).get("flag", False)))
        gui.landmark_visibility[lm] = vis_var
        gui.landmark_found[lm] = found_var
        gui.landmark_flagged[lm] = flag_var
        tk.Checkbutton(
            gui.landmark_table,
            variable=vis_var,
            command=gui._draw_points,
            font=gui.dialogue_font,
        ).grid(row=i, column=0, sticky="w", padx=(2, 4), pady=1)
        rb = tk.Radiobutton(
            gui.landmark_table,
            text=lm,
            variable=gui.selected_landmark,
            value=lm,
            anchor="w",
            justify="left",
            command=lambda gui=gui: on_landmark_selected(gui),
            font=gui.dialogue_font,
        )
        rb.grid(row=i, column=1, sticky="w", padx=(2, 4), pady=1)
        gui.landmark_radio_widgets[lm] = rb

        found_cb = tk.Checkbutton(
            gui.landmark_table,
            text="",
            variable=found_var,
            font=gui.dialogue_font,
            indicatoron=True,
            takefocus=0,
            command=lambda lm=lm, gui=gui: on_annotated_checkbox_toggled(gui, lm),
        )
        found_cb.grid(row=i, column=2, sticky="w", padx=(2, 4), pady=1)
        gui.landmark_found_widgets[lm] = found_cb

        flag_cb = tk.Checkbutton(
            gui.landmark_table,
            text="",
            variable=flag_var,
            font=gui.dialogue_font,
            indicatoron=True,
            takefocus=0,
            command=lambda lm=lm, gui=gui: on_flag_checkbox_toggled(gui, lm),
        )
        flag_cb.grid(row=i, column=3, sticky="w", padx=(2, 4), pady=1)
        gui.landmark_flag_widgets[lm] = flag_cb

    if visible_landmarks and not gui.selected_landmark.get():
        gui.selected_landmark.set(visible_landmarks[0])
    elif not visible_landmarks:
        gui.selected_landmark.set("")

    load_note_for_selected_landmark(gui)
    gui._bind_landmark_scroll(True)


def on_landmark_selected(gui: AnnotationGUI) -> None:
    lm = gui.selected_landmark.get()
    gui._apply_settings_to_ui_for(lm)
    gui._sync_auto_tools_for_selected_landmark()
    load_note_for_selected_landmark(gui)
    gui._draw_points()
    gui._refresh_zoom_landmark_overlay()
    if gui.last_mouse_canvas_pos is not None:
        gui._update_line_preview(*gui.last_mouse_canvas_pos)
    else:
        gui._clear_line_preview()
    gui._update_femoral_axis_overlay()
    gui.after_idle(gui._scroll_landmark_into_view, lm)
    if gui._landmark_ref_dialog is not None:
        gui._landmark_ref_dialog.update_landmark(lm)


def on_flag_checkbox_toggled(gui: AnnotationGUI, lm: str) -> None:
    if gui.current_image_path is None:
        return

    flag_var = gui.landmark_flagged.get(lm)
    is_flagged = flag_var.get() if flag_var is not None else False
    gui._set_landmark_flag(lm, is_flagged)

    if not is_flagged:
        gui._set_landmark_note(lm, "")

    if gui.selected_landmark.get() == lm:
        load_note_for_selected_landmark(gui)

    gui.dirty = True
    gui._maybe_autosave_current_image()

    pts, _quality = gui._get_annotations()
    update_found_checks(gui, pts)
    gui._draw_points()


def on_annotated_checkbox_toggled(gui: AnnotationGUI, lm: str) -> None:
    if gui.current_image_path is None:
        return

    pts, _quality = gui._get_annotations()
    found_var = gui.landmark_found.get(lm)
    is_checked = found_var.get() if found_var is not None else False

    if not is_checked:
        if lm not in pts:
            gui.landmark_found[lm].set(False)
            update_found_checks(gui, pts)
            return

        confirmed = messagebox.askyesno(
            "Delete Landmark",
            f'Are you sure you want to delete "{lm}"?\n\n'
            "All information for this landmark, including any flag and notes, will be deleted.",
        )

        if not confirmed:
            gui.landmark_found[lm].set(True)
            update_found_checks(gui, pts)
            return

        del pts[lm]
        key = (
            gui._path_key(gui.current_image_path)
            if gui.json_path is not None
            else str(gui.current_image_path)
        )
        if key in gui.landmark_meta:
            gui.landmark_meta[key].pop(lm, None)

        if gui._is_line_landmark(lm):
            gui._clear_line_preview()

        if lm in ("LOB", "ROB"):
            gui.last_seed.pop(lm, None)
            if str(gui.current_image_path) in gui.seg_masks:
                gui.seg_masks[str(gui.current_image_path)].pop(lm, None)
            gui._remove_overlay_for(lm)

        gui._clear_femoral_axis_overlay()
        gui.dirty = True
        gui._maybe_autosave_current_image()
        gui._draw_points()
        gui._refresh_zoom_landmark_overlay()
        load_note_for_selected_landmark(gui)
        gui._refresh_image_listbox()
        return

    if lm not in pts:
        gui.landmark_found[lm].set(False)
        update_found_checks(gui, pts)


def update_found_checks(gui: AnnotationGUI, pts_dict) -> None:
    key = (
        gui._path_key(gui.current_image_path)
        if gui.json_path is not None and gui.current_image_path is not None
        else str(gui.current_image_path)
    )
    meta = gui.landmark_meta.get(key, {})

    for lm in gui.landmarks:
        var = gui.landmark_found.get(lm)
        widget = gui.landmark_found_widgets.get(lm)
        if var is not None:
            is_found = lm in pts_dict
            var.set(is_found)

            if widget is not None:
                found_widget = cast(tk.Checkbutton, widget)
                try:
                    found_widget.configure(
                        fg="green" if is_found else "black",
                        activeforeground="green" if is_found else "black",
                        selectcolor="#90EE90" if is_found else found_widget.cget("bg"),
                    )
                except Exception:
                    pass

        fvar = gui.landmark_flagged.get(lm)
        fwidget = gui.landmark_flag_widgets.get(lm)
        is_flagged = bool(meta.get(lm, {}).get("flag", False))
        if fvar is not None:
            fvar.set(is_flagged)
        if fwidget is not None:
            flag_widget = cast(tk.Checkbutton, fwidget)
            try:
                flag_widget.configure(
                    fg="red" if is_flagged else "black",
                    activeforeground="red" if is_flagged else "black",
                    selectcolor="#FFB6B6" if is_flagged else flag_widget.cget("bg"),
                )
            except Exception:
                pass


def load_note_for_selected_landmark(gui: AnnotationGUI) -> None:
    if gui.note_text is None:
        return

    lm = gui.selected_landmark.get()
    can_edit = bool(lm) and gui._get_landmark_flag(lm)
    note = gui._get_landmark_note(lm) if can_edit else ""

    gui.note_text_internal_update = True
    gui.note_text.configure(state="normal")
    gui.note_text.delete("1.0", "end")
    gui.note_text.insert("1.0", note)
    gui.note_text.edit_modified(False)
    gui.note_text_internal_update = False

    set_note_editor_enabled(gui, can_edit)


def save_note_for_selected_landmark(gui: AnnotationGUI) -> None:
    if gui.note_text is None or gui.current_image_path is None:
        return

    lm = gui.selected_landmark.get()
    if not lm:
        return

    if not gui._get_landmark_flag(lm):
        gui._set_landmark_note(lm, "")
        return

    note = gui.note_text.get("1.0", "end-1c")
    gui._set_landmark_note(lm, note)


def set_note_editor_enabled(gui: AnnotationGUI, enabled: bool) -> None:
    if gui.note_text is None:
        return

    if enabled:
        gui.note_text.configure(
            state="normal",
            bg="white",
            fg="black",
            insertbackground="black",
        )
    else:
        gui.note_text.configure(
            state="disabled",
            bg="#E6E6E6",
            fg="#666666",
            insertbackground="#666666",
        )


def on_note_text_modified(gui: AnnotationGUI, _event=None) -> None:
    if gui.note_text is None:
        return
    if gui.note_text_internal_update:
        gui.note_text.edit_modified(False)
        return
    if not gui.note_text.edit_modified():
        return

    save_note_for_selected_landmark(gui)
    gui.note_text.edit_modified(False)
    gui.dirty = True
    gui._maybe_autosave_current_image()


def set_all_visibility(gui: AnnotationGUI, value: bool) -> None:
    for var in gui.landmark_visibility.values():
        var.set(value)
    gui._draw_points()


def get_allowed_landmarks_for_current_view(gui: AnnotationGUI) -> set[str]:
    view = gui.current_view_var.get().strip()
    if not view:
        return set()
    return set(gui.allowed_views.get(view, []))


def on_view_selected(gui: AnnotationGUI, _event=None) -> None:
    new_view = gui.current_view_var.get().strip()
    if new_view not in gui.allowed_views:
        return
    gui._set_current_view(new_view)
    gui._maybe_autosave_current_image()
    gui.focus_set()


def on_image_direction_changed(gui: AnnotationGUI, _event=None) -> None:
    gui.current_image_direction = gui.image_direction_var.get()
    record = gui._get_current_image_record()
    if record is not None:
        record["image_direction"] = gui.current_image_direction
    gui._maybe_autosave_current_image()
    gui.focus_set()


def bind_landmark_scroll(gui: AnnotationGUI, bind: bool) -> None:
    if bind:
        gui.lp_canvas.bind_all("<MouseWheel>", gui._landmark_mousewheel)
    else:
        gui.lp_canvas.unbind_all("<MouseWheel>")


def landmark_mousewheel(gui: AnnotationGUI, event) -> None:
    delta = -1 if event.delta > 0 else 1
    gui.lp_canvas.yview_scroll(delta, "units")


def scroll_landmark_into_view(gui: AnnotationGUI, lm: str) -> None:
    rb = cast(tk.Widget | None, getattr(gui, "landmark_radio_widgets", {}).get(lm))
    if rb is None:
        return
    gui.lp_canvas.update_idletasks()
    bbox = gui.lp_canvas.bbox("all")
    if not bbox:
        return
    y1, y2 = bbox[1], bbox[3]
    total = max(1, y2 - y1)
    canvas_h = gui.lp_canvas.winfo_height()
    vis_top = gui.lp_canvas.canvasy(0)
    vis_bottom = vis_top + canvas_h
    item_top = gui._widget_y_in_inner(rb)
    item_bottom = item_top + rb.winfo_height()
    pad = 6
    if item_top < vis_top:
        new_top = max(y1, item_top - pad)
        gui.lp_canvas.yview_moveto((new_top - y1) / total)
    elif item_bottom > vis_bottom:
        new_top = min(item_bottom + pad - canvas_h, y2 - canvas_h)
        new_top = max(y1, new_top)
        gui.lp_canvas.yview_moveto((new_top - y1) / total)


def get_landmark_meta(gui: AnnotationGUI, lm: str) -> dict[str, bool | str]:
    if gui.current_image_path is None:
        return {"flag": False, "note": ""}

    key = (
        gui._path_key(gui.current_image_path)
        if gui.json_path is not None
        else str(gui.current_image_path)
    )
    per_img = gui.landmark_meta.setdefault(key, {})
    return per_img.setdefault(lm, {"flag": False, "note": ""})


def set_landmark_flag(gui: AnnotationGUI, lm: str, value: bool) -> None:
    meta = gui._get_landmark_meta(lm)
    meta["flag"] = bool(value)


def get_landmark_flag(gui: AnnotationGUI, lm: str) -> bool:
    return bool(gui._get_landmark_meta(lm).get("flag", False))


def set_landmark_note(gui: AnnotationGUI, lm: str, note: str) -> None:
    meta = gui._get_landmark_meta(lm)
    meta["note"] = note


def get_landmark_note(gui: AnnotationGUI, lm: str) -> str:
    return str(gui._get_landmark_meta(lm).get("note", ""))


def change_selected_landmark(gui: AnnotationGUI, step: int) -> None:
    if not getattr(gui, "landmarks", None):
        return
    if not gui.landmarks:
        return
    current = gui.selected_landmark.get()
    if current in gui.landmarks:
        idx = gui.landmarks.index(current)
    else:
        idx = 0
    idx = idx + step
    if idx < 0 or idx >= len(gui.landmarks):
        return
    new_lm = gui.landmarks[idx]
    if new_lm != current:
        gui.selected_landmark.set(new_lm)
        gui._on_landmark_selected()


def on_arrow_up(gui: AnnotationGUI, _event=None) -> str:
    change_selected_landmark(gui, -1)
    return "break"


def on_arrow_down(gui: AnnotationGUI, _event=None) -> str:
    change_selected_landmark(gui, 1)
    return "break"


def delete_current_landmark(gui: AnnotationGUI) -> None:
    """
    The goal of this function is to remove the annotation from the current landmark. When saving. I'm going to make.
    """
    lm = gui.selected_landmark.get()
    if not lm:
        messagebox.showwarning("No Landmark", "Please select a landmark in the list")
        return

    current_pts = gui.annotations.setdefault(str(gui.current_image_path), {})
    if lm in current_pts:
        # Delete it if it does
        del current_pts[lm]

    if gui._is_line_landmark(lm):
        gui._clear_line_preview()

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
        gui._store_current_settings_for(lm)
        gui._resegment_for(lm)
    # Auto-save to database immediately after deleting landmark
    gui._auto_save_to_db()
    return


def widget_y_in_inner(gui: AnnotationGUI, widget: tk.Misc) -> int:
    y = 0
    w: tk.Misc | None = widget
    while w is not None and w is not gui.lp_inner:
        y += w.winfo_y()
        parent_name = w.winfo_parent()
        if not parent_name:
            break
        w = cast(tk.Misc | None, w.nametowidget(parent_name))
    return y
