"""Keyboard shortcuts, help dialog, tool syncing, misc handlers."""

from __future__ import annotations

# pyright: reportDeprecated=false, reportUnusedImport=false, reportUnusedCallResult=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportImplicitStringConcatenation=false

import logging
import platform
import sqlite3
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any, Optional, cast

import cv2  # pyright: ignore[reportMissingImports]

from dataset_config import get_dataset_dest  # pyright: ignore[reportImplicitRelativeImport]
from downloader import download_dataset  # pyright: ignore[reportImplicitRelativeImport]
from landmark_reference import LandmarkReference  # pyright: ignore[reportImplicitRelativeImport]
from landmark_reference_dialog import LandmarkReferenceDialog  # pyright: ignore[reportImplicitRelativeImport]
from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]

if TYPE_CHECKING:
    from typing import Any as AnnotationGUI

logger = logging.getLogger(__name__)


def on_space(gui: AnnotationGUI) -> None:
    """
    Here, we are marking the current image as "verified" in the table
    """

    if gui.db_path is not None:
        try:
            with sqlite3.connect(gui.db_path) as conn:
                cur = conn.cursor()
                if gui.absolute_current_image_path is None:
                    return
                image_filename = extract_filename(gui.absolute_current_image_path)

                cur.execute(
                    """
                    INSERT INTO annotations (image_filename, verified)
                    VALUES (?, 1)
                    ON CONFLICT(image_filename) DO UPDATE
                    SET verified = 1-annotations.verified
                    """,
                    (image_filename,),
                )
                conn.commit()
            gui._draw_points()
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Failed to toggle verification status:\n{e}",
            )
    return


def is_current_image_verified(gui: AnnotationGUI) -> bool:
    if gui.db_path is not None:
        try:
            with sqlite3.connect(gui.db_path) as conn:
                cur = conn.cursor()
                if gui.absolute_current_image_path is None:
                    return False

                query = """
                    SELECT verified FROM annotations WHERE image_filename = ?
                """
                image_fname = extract_filename(gui.absolute_current_image_path)

                cur.execute(
                    query,
                    (image_fname,),
                )
                row = cur.fetchone()
            return bool(row[0] if row else False)
        except sqlite3.Error:
            # Silently return False if we can't check - non-critical operation
            return False
    return False


def initial_dl_status(gui: AnnotationGUI) -> str:
    app = cast(Any, gui)

    if not app._datasets_config.datasets:
        return "No datasets configured."

    name = app._selected_ds_name.get()
    dataset = next(
        (ds for ds in app._datasets_config.datasets if ds.name == name), None
    )
    if not dataset:
        return "Select a dataset."

    dest = get_dataset_dest(dataset)
    if dest.exists() and any(dest.iterdir()):
        return f"Data folder exists: {dataset.subfolder}"
    return f"Will download to: {dataset.subfolder}"


def on_download_data(gui: AnnotationGUI) -> None:
    app = cast(Any, gui)

    name = app._selected_ds_name.get()
    dataset = next(
        (ds for ds in app._datasets_config.datasets if ds.name == name), None
    )
    if not dataset:
        return

    # Guard against accidental re-download
    dest = get_dataset_dest(dataset)
    if dest.exists() and any(dest.iterdir()):
        n_files = sum(1 for _ in dest.rglob("*") if _.is_file())
        if not messagebox.askyesno(
            "Dataset Already Exists",
            f"'{dataset.name}' already has {n_files} file(s) "
            f"in:\n{dest}\n\nDownload again? "
            f"(Existing files will be overwritten.)",
        ):
            return

    app._dl_button.config(state="disabled")
    app._dl_status_var.set("Starting download…")

    def on_progress(msg: str) -> None:
        gui.after(0, lambda m=msg: app._dl_status_var.set(m))

    def on_done(exc: Optional[Exception]) -> None:
        if exc is None:
            gui.after(
                0,
                lambda: (
                    app._dl_status_var.set(f"Download complete: {dataset.subfolder}"),
                    app._dl_button.config(state="normal"),
                ),
            )
        else:
            gui.after(
                0,
                lambda e=exc: (
                    app._dl_status_var.set(f"Download failed: {e}"),
                    app._dl_button.config(state="normal"),
                    messagebox.showerror(
                        "Download Failed",
                        f"Could not download study data:\n\n{e}",
                    ),
                ),
            )

    download_dataset(
        dataset=dataset,
        method=app._datasets_config.download_method,
        on_progress=on_progress,
        on_done=on_done,
    )


def on_image_flag_widget_changed(gui: AnnotationGUI) -> None:
    gui.current_image_flag = bool(gui.image_flag_var.get())
    record = gui._get_current_image_record()
    if record is not None:
        record["image_flag"] = gui.current_image_flag

    refresh_image_flag_checkbox_style(gui)

    gui.dirty = True
    gui._maybe_autosave_current_image()


def refresh_image_flag_checkbox_style(gui: AnnotationGUI) -> None:
    if gui.image_flag_check is None:
        return

    is_flagged = bool(gui.image_flag_var.get())

    try:
        gui.image_flag_check.configure(
            fg="black",
            activeforeground="black",
            disabledforeground="black",
            selectcolor="#FFB6B6" if is_flagged else gui.cget("bg"),
        )
    except Exception:
        pass


def bind_shortcut(gui: AnnotationGUI, sequence: str, callback) -> None:
    def wrapper(event):
        if note_text_shortcuts_blocked(gui):
            return "break"
        return callback(event)

    gui.bind(sequence, wrapper)


def note_text_shortcuts_blocked(gui: AnnotationGUI) -> bool:
    if gui.note_text is None:
        return False

    try:
        if str(gui.note_text.cget("state")) != "normal":
            return False
    except Exception:
        return False

    focused = gui.focus_get() is gui.note_text

    try:
        px, py = gui.winfo_pointerxy()
        hovered_widget = gui.winfo_containing(px, py)
    except Exception:
        hovered_widget = None

    hovered = hovered_widget is gui.note_text or (
        hovered_widget is not None
        and str(hovered_widget).startswith(str(gui.note_text))
    )

    return focused and hovered


def sync_auto_tools(gui: AnnotationGUI) -> None:
    lm = gui.selected_landmark.get().strip()

    hover_landmarks = {"L-FHC", "R-FHC", "L-AC", "R-AC"}
    femoral_axis_landmarks = {"L-FA", "R-FA"}

    want_hover = lm in hover_landmarks
    want_femoral_axis = lm in femoral_axis_landmarks

    if want_hover:
        if not gui.hover_enabled.get():
            gui.hover_enabled.set(True)
        if gui.femoral_axis_enabled.get():
            gui.femoral_axis_enabled.set(False)
        gui._toggle_hover()
        gui._toggle_femoral_axis()
        return

    if want_femoral_axis:
        if not gui.femoral_axis_enabled.get():
            gui.femoral_axis_enabled.set(True)
        if gui.hover_enabled.get():
            gui.hover_enabled.set(False)
        gui._toggle_femoral_axis()
        gui._toggle_hover()
        return

    changed = False

    if gui.hover_enabled.get():
        gui.hover_enabled.set(False)
        changed = True

    if gui.femoral_axis_enabled.get():
        gui.femoral_axis_enabled.set(False)
        changed = True

    if changed:
        gui._toggle_hover()
        gui._toggle_femoral_axis()
    else:
        gui._hide_hover_circle()
        gui._clear_femoral_axis_overlay()


def on_pg_down(gui: AnnotationGUI) -> None:
    gui._next_image()
    return


def on_pg_up(gui: AnnotationGUI) -> None:
    gui._prev_image()
    return


def on_backspace(gui: AnnotationGUI) -> None:
    gui._delete_current_landmark()
    return


def on_1_press(gui: AnnotationGUI) -> None:
    gui.change_image_quality(1)
    return


def on_2_press(gui: AnnotationGUI) -> None:
    gui.change_image_quality(2)
    return


def on_3_press(gui: AnnotationGUI) -> None:
    gui.change_image_quality(3)
    return


def on_4_press(gui: AnnotationGUI) -> None:
    gui.change_image_quality(4)
    return


def change_radius(gui: AnnotationGUI, delta: int) -> None:
    new_r = max(1, min(300, gui.hover_radius.get() + delta))
    if new_r != gui.hover_radius.get():
        gui.hover_radius.set(new_r)
        gui._on_radius_change(str(new_r))


def resegment_selected_if_needed(gui: AnnotationGUI) -> None:
    lm = gui.selected_landmark.get()
    if lm in ("LOB", "ROB"):
        gui._store_current_settings_for(lm)
        resegment_for(gui, lm)


def resegment_for(
    gui: AnnotationGUI,
    lm: str,
    apply_saved_settings: bool = False,
) -> None:
    if gui.current_image_path is None:
        return
    seed = gui.last_seed.get(lm)
    if seed is None or cv2 is None or gui.current_image is None:
        return
    x, y = seed
    mask = gui._segment_with_fallback(x, y, lm)

    if mask is None:
        return
    mask = gui._grow_shrink(mask, gui.grow_shrink.get())
    gui.seg_masks.setdefault(str(gui.current_image_path), {})[lm] = mask
    gui._update_overlay_for(lm)


def on_arrow_left(gui: AnnotationGUI) -> None:
    gui._set_selected_visibility(False)


def on_arrow_right(gui: AnnotationGUI) -> None:
    gui._set_selected_visibility(True)


def format_shortcuts(
    rows,
    width: int = 60,
    gap_min: int = 2,
    leader: str = ".",
):
    """
    2-column text block with an 'hfill' made of leader characters (e.g. dots).
    Looks good even with proportional fonts.
    """

    key_w = max(len(k) for k, _ in rows)
    lines = []

    for keys, action in rows:
        left = f"{keys:<{key_w}}"
        # Fill the middle with dots/spaces so the action ends at width-ish
        fill_len = max(gap_min, width - len(left) - len(action))
        fill = (leader * fill_len) if leader else (" " * fill_len)
        lines.append(f"{left} {fill} {action}")

    return "\n".join(lines)


def on_h_press(gui: AnnotationGUI) -> None:
    shortcuts = [
        ("<up> / ↑ / d", "Previous landmark"),
        ("<down> / ↓ / f", "Next landmark"),
        ("<left> / <--", "Hide selected landmark"),
        ("<right> / -->", "Show selected landmark"),
        ("b / Ctrl+b", "Previous image"),
        ("n / Ctrl+n", "Next image"),
        ("1–4", "Set image quality (1-worst, 4-best)"),
        ("Backspace", "Delete selected landmark"),
        ("h", "Show this help"),
        ("?", "Show landmark reference"),
        ("Mouse click", "Place landmark"),
        ("Mouse wheel", "Adjust hover radius"),
    ]
    help_text = format_shortcuts(
        shortcuts,
        width=60,
        leader=".",
    )

    win = tk.Toplevel(gui)
    win.title("Help & Keyboard Shortcuts")
    win.transient(gui)
    win.resizable(False, False)

    frm = ttk.Frame(win, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(
        frm,
        text="Keyboard Shortcuts",
        font=gui.heading_font,
    ).pack(anchor="w", pady=(0, 8))

    text = tk.Text(
        frm,
        wrap="none",
        height=len(shortcuts) + 1,
        borderwidth=0,
        highlightthickness=0,
    )
    text.pack(fill="both", expand=True)

    text.configure(font=gui.dialogue_font)

    text.insert("1.0", help_text)
    text.configure(state="disabled")

    ttk.Button(
        frm,
        text="Close",
        command=win.destroy,
    ).pack(anchor="e", pady=(10, 0))


def open_landmark_reference(gui: AnnotationGUI) -> None:
    """Open or focus the landmark reference popup."""
    if gui._landmark_ref is None:
        return

    if gui._landmark_ref_dialog is not None:
        try:
            gui._landmark_ref_dialog.lift()
            gui._landmark_ref_dialog.focus_force()
            return
        except tk.TclError:
            # Window was destroyed outside our tracking
            gui._landmark_ref_dialog = None

    gui._landmark_ref_dialog = LandmarkReferenceDialog(
        parent=gui,
        reference=gui._landmark_ref,
        current_landmark=gui.selected_landmark.get() or None,
        on_close=gui._on_landmark_ref_dialog_closed,
    )


def on_landmark_ref_dialog_closed(gui: AnnotationGUI) -> None:
    """Clear the dialog reference when the popup is closed."""
    gui._landmark_ref_dialog = None


def configure_linux_fonts(gui: AnnotationGUI) -> None:
    if platform.system() != "Linux" and not sys.platform.startswith("linux"):
        return

    # (optional) scaling tweak, only on Linux
    gui.tk.call("tk", "scaling", 1.25)

    # Pick whatever you decided works well in your env
    gui.heading_font = tkfont.Font(family="Liberation Sans", size=15, weight="bold")
    gui.dialogue_font = tkfont.Font(family="Liberation Sans", size=12, weight="bold")

    # Tk named fonts (classic tk widgets)
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
    ):
        f = tkfont.nametofont(name)
        f.configure(family="Liberation Sans", size=12)

    # ttk styles
    style = ttk.Style(gui)
    style.theme_use(style.theme_use())  # force theme init / refresh

    style.configure(".", font=gui.dialogue_font)
    for s in (
        "TLabel",
        "TButton",
        "TCheckbutton",
        "TRadiobutton",
        "TEntry",
        "TCombobox",
        "TMenubutton",
        "TNotebook",
        "TNotebook.Tab",
        "Treeview",
        "Treeview.Heading",
        "TLabelframe.Label",
    ):
        style.configure(s, font=gui.dialogue_font)
    return


def change_method_to_ff(gui: AnnotationGUI) -> None:
    gui.use_adap_cc.set(False)
    gui.use_ff.set(True)
    gui.method.set("Flood Fill")
    return


def change_method_to_acc(gui: AnnotationGUI) -> None:
    gui.use_adap_cc.set(True)
    gui.use_ff.set(False)
    gui.method.set("Adaptive CC")
    return
