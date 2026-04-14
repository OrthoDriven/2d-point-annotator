"""Image session — loading, navigation, queue management."""

# pyright: reportMissingImports=false, reportUnusedImport=false, reportDeprecated=false, reportUnnecessaryTypeIgnoreComment=false, reportArgumentType=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnusedCallResult=false, reportAttributeAccessIssue=false, reportUnnecessaryComparison=false, reportImplicitStringConcatenation=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false, reportImportCycles=false

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import tkinter as tk
from pathlib import Path, PurePath
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

import numpy as np  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingImports]
from PIL import Image  # pyright: ignore[reportMissingImports]

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

from dirs import BASE_DIR  # pyright: ignore[reportImplicitRelativeImport]
from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]

__all__ = [
    "check_csv_images",
    "exit_csv_check_mode",
    "exit_queue_mode",
    "find_unannotated_images",
    "get_csv_images_from_directory",
    "get_current_image_record",
    "image_progress_done",
    "image_progress_text",
    "load_data",
    "load_image",
    "load_image_from_path",
    "next_image",
    "on_image_list_select",
    "on_close",
    "prev_image",
    "prompt_for_view_if_needed",
    "prune_annotations_for_current_view",
    "refresh_image_listbox",
    "rebuild_landmark_panel_for_view",
    "resolve_image_path",
    "set_current_view",
    "sync_current_state_to_json_record",
    "update_queue_status",
    "count_allowed_landmarks",
    "count_completed_landmarks",
]


def _get_data_dir() -> Path:
    for module_name in ("__main__", "main"):
        module = sys.modules.get(module_name)
        getter = getattr(module, "get_data_dir", None)
        if callable(getter):
            try:
                data_dir = getter()
            except Exception:
                continue
            if isinstance(data_dir, Path):
                return data_dir
            return Path(data_dir)
    return BASE_DIR


def load_data(gui: AnnotationGUI) -> None:
    if not gui._maybe_save_before_destructive_action("load another data file"):
        return

    data_dir = _get_data_dir()
    initial = data_dir if data_dir.is_dir() else BASE_DIR
    json_file = filedialog.askopenfilename(
        initialdir=initial,
        filetypes=[("JSON File", "*.json")],
        title="Load annotation data JSON",
    )
    if not json_file:
        return

    try:
        json_path = Path(json_file)
        with json_path.open("r", encoding="utf-8") as handle:
            raw_data: object = json.load(handle)  # pyright: ignore[reportAny]
    except Exception as e:
        messagebox.showerror("Load Data", f"Failed to read JSON:\n{e}")
        return

    if not isinstance(raw_data, dict):
        messagebox.showerror("Load Data", "JSON root must be an object.")
        return

    landmarks = raw_data.get("landmarks")
    views = raw_data.get("views")
    images = raw_data.get("images")

    if not isinstance(landmarks, list) or not all(
        isinstance(name, str) and name.strip() for name in landmarks
    ):
        messagebox.showerror(
            "Load Data", 'JSON must contain a "landmarks" list of names.'
        )
        return

    if not isinstance(views, dict) or not views:
        messagebox.showerror(
            "Load Data", 'JSON must contain a non-empty "views" mapping.'
        )
        return

    if not isinstance(images, list):
        messagebox.showerror("Load Data", 'JSON must contain an "images" list.')
        return

    allowed_views: dict[str, list[str]] = {}
    for view_name, landmark_list in views.items():
        if not isinstance(view_name, str) or not view_name.strip():
            messagebox.showerror(
                "Load Data", "All view names must be non-empty strings."
            )
            return
        if not isinstance(landmark_list, list) or not all(
            isinstance(name, str) for name in landmark_list
        ):
            messagebox.showerror(
                "Load Data",
                f'View "{view_name}" must map to a list of landmark names.',
            )
            return
        allowed_views[view_name] = list(landmark_list)

    gui.json_path = json_path
    gui.json_dir = json_path.parent
    gui.allowed_views = allowed_views
    gui.json_data = {
        "landmarks": list(landmarks),
        "views": dict(gui.allowed_views),
        "images": [],
    }
    gui.landmarks = list(landmarks)
    gui.images = []
    gui.image_index_map = {}
    gui.current_image_index = -1
    gui.saved_image_snapshots = {}
    gui.annotations.clear()
    gui.lm_settings.clear()
    gui.landmark_meta.clear()
    gui.seg_masks.clear()
    gui.last_seed.clear()
    gui.queue_mode = False
    gui.check_csv_mode = False
    gui.current_view_var.set("")

    if gui.view_dropdown is not None:
        gui.view_dropdown["values"] = list(gui.allowed_views.keys())

    missing: list[str] = []
    for idx, raw_record in enumerate(images):
        if not isinstance(raw_record, dict):
            missing.append(f"images[{idx}] is not an object")
            continue
        if "image_path" not in raw_record:
            missing.append(f"images[{idx}] is missing image_path")
            continue

        resolved = gui._resolve_image_path(str(raw_record["image_path"]))
        record = dict(raw_record)
        record.setdefault("image_flag", False)
        record.setdefault("view", None)
        record.setdefault("annotations", {})
        record["resolved_image_path"] = str(resolved)
        gui.json_data["images"].append(record)

        if not resolved.exists():
            missing.append(str(resolved))
            continue

        key = gui._path_key(resolved)
        gui.images.append(resolved)
        gui.image_index_map[key] = len(gui.json_data["images"]) - 1

    gui._build_landmark_panel()

    if missing:
        preview = "\n".join(missing[:15])
        more = "" if len(missing) <= 15 else f"\n... and {len(missing) - 15} more"
        messagebox.showwarning(
            "Missing image paths",
            f"Some image paths from the JSON could not be found:\n\n{preview}{more}",
        )

    if not gui.images:
        gui.current_image = None
        gui.current_image_path = None
        gui.absolute_current_image_path = None
        gui.current_image_index = -1
        gui.current_image_flag = False
        gui.path_var.set("No valid images found in JSON")
        gui.quality_var.set("0")
        gui.current_view_var.set("")
        gui.canvas.delete("all")
        gui._render_black_zoom_view()
        gui.dirty = False
        refresh_image_listbox(gui)
        return

    gui.current_image_index = 0
    load_image_from_path(gui, gui.images[0])

    if gui.selected_landmark.get():
        gui._on_landmark_selected()

    for image_path in gui.images:
        gui.saved_image_snapshots[gui._path_key(image_path)] = (
            gui._canonical_image_state_for_path(image_path)
        )

    refresh_image_listbox(gui)


def load_image_from_path(gui: AnnotationGUI, path: Path) -> None:
    try:
        gui.current_image = Image.open(path)

        if gui.current_image.mode == "I;16":
            arr = np.array(gui.current_image, dtype=np.uint16)

            lo = np.percentile(arr, 1)
            hi = np.percentile(arr, 99)

            arr = np.clip(arr, lo, hi)
            arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)

            img = Image.fromarray(arr, mode="L").convert("RGB")
            gui.current_image = img
        gui.current_image = gui.current_image.convert("RGB")

    except Exception as e:
        messagebox.showerror("Load Image", f"Failed to open image:\n{e}")
        return

    json_record_loaded = gui.json_path is not None and gui.images
    if gui.view_dropdown is not None:
        gui.view_dropdown["values"] = list(gui.allowed_views.keys())

    if json_record_loaded:
        resolved_path = path.resolve()
        gui.current_image_path = resolved_path
        gui.absolute_current_image_path = resolved_path
        gui.current_image_index = (
            gui.images.index(resolved_path) if resolved_path in gui.images else -1
        )
        key = gui._path_key(resolved_path)
        record = gui._get_current_image_record()
        if record is not None:
            gui.current_image_flag = bool(record.get("image_flag", False))
            gui.image_flag_var.set(gui.current_image_flag)
            gui.current_image_direction = record.get("image_direction", "AP") or "AP"
            gui.image_direction_var.set(gui.current_image_direction)
            gui.annotations[key] = gui._parse_annotations_for_record(record)
        else:
            gui.current_image_flag = False
            gui.image_flag_var.set(False)
            gui.current_image_direction = "AP"
            gui.image_direction_var.set("AP")
            gui.annotations[key] = {}
            gui.landmark_meta[key] = {}
        gui.current_image_quality = 0
        gui.current_view_var.set(gui._get_current_view())
    else:
        rel_path = PurePath(path.resolve()).relative_to(
            BASE_DIR.resolve(), walk_up=True
        )
        gui.current_image_path = Path(rel_path)
        gui.absolute_current_image_path = path.resolve()
        gui.current_image_flag = False
        gui.image_flag_var.set(False)
        gui.current_image_direction = "AP"
        gui.image_direction_var.set("AP")
        gui.current_view_var.set("")

    gui._refresh_image_flag_checkbox_style()

    w, h = gui.current_image.size
    gui.canvas.config(width=w, height=h)
    gui.canvas.delete("all")
    gui.base_img_item = None
    gui._remove_all_overlays()
    gui.last_seed.clear()
    gui._clear_line_preview()
    gui._clear_femoral_axis_overlay()
    gui.dragging_landmark = None
    gui.dragging_point_index = None
    gui.dragging_line_whole = False
    gui.dragging_line_last_img_pos = None

    current_key = (
        gui._path_key(gui.current_image_path)
        if json_record_loaded and gui.current_image_path is not None
        else str(gui.current_image_path)
    )
    gui.lm_settings.setdefault(current_key, {})
    gui.annotations.setdefault(current_key, {})

    if not json_record_loaded:
        gui.load_points(show_message=False)

    gui._render_base_image()
    gui.mouse_crosshair_ids = []
    gui.extended_crosshair_ids = []
    gui.zoom_extended_crosshair_ids = []
    gui._hide_hover_circle()
    gui.last_mouse_canvas_pos = None
    gui._update_zoom_view(None, None)
    gui._hide_zoom_extended_crosshair()
    gui.dirty = False
    gui._update_path_var()
    gui.dirty = False

    if json_record_loaded:
        gui._prompt_for_view_if_needed()
    else:
        gui._rebuild_landmark_panel_for_view()

    gui._load_note_for_selected_landmark()

    pts, _quality = gui._get_annotations()
    gui._update_found_checks(pts)
    gui._draw_points()

    if json_record_loaded:
        gui._refresh_saved_snapshot_for_current_image()

    refresh_image_listbox(gui)


def load_image(gui: AnnotationGUI) -> None:
    if not gui._maybe_save_before_destructive_action("load another image"):
        return
    abs_path = filedialog.askopenfilename(
        initialdir=BASE_DIR,
        filetypes=[("Image files", ("*.png", "*.jpg", "*.jpeg", "*.bmp", ".tif"))],
    )
    if not abs_path:
        return

    gui.absolute_current_image_path = Path(abs_path)
    load_image_from_path(gui, Path(abs_path))
    if gui.landmarks:
        gui.selected_landmark.set(gui.landmarks[0])

    return


def next_image(gui: AnnotationGUI) -> None:
    if gui.json_path is not None and gui.images:
        if gui.current_image_index >= len(gui.images) - 1:
            messagebox.showwarning(
                "End of List", "You have reached the last image in the JSON."
            )
            return

        if not gui._maybe_save_before_destructive_action("switch images"):
            return

        gui._navigation_in_progress = True
        gui._suspend_image_tree_select = True
        try:
            gui.current_image_index += 1
            load_image_from_path(gui, gui.images[gui.current_image_index])
        finally:
            gui._navigation_in_progress = False
            gui._suspend_image_tree_select = False
        return

    gui.save_annotations()
    if gui.queue_mode:
        if gui.queue_index >= len(gui.unannotated_queue) - 1:
            messagebox.showwarning(
                "Start of Queue",
                "You're at the beginning of the unannotated images.",
            )
            return

        gui.queue_index += 1
        prev_path = gui.unannotated_queue[gui.queue_index]
        gui.absolute_current_image_path = prev_path
        load_image_from_path(gui, prev_path)
        gui._update_queue_status()

    elif gui.check_csv_mode:
        if gui.csv_index >= len(gui.csv_path_queue) - 1:
            return
        gui.csv_index += 1
        prev_path = gui.csv_path_queue[gui.csv_index]
        gui.absolute_current_image_path = prev_path
        load_image_from_path(gui, Path(prev_path))
        gui._update_queue_status()

    else:
        idx, all_files = gui._get_image_index_from_directory()
        current_path = gui.absolute_current_image_path
        if current_path is None or not all_files:
            return
        if len(all_files) == idx + 1:
            messagebox.showwarning(
                "End of Directory",
                "You've reached the end of the current image directory, please use"
                "'Load Image' to find a new image, or use 'Prev Image' to move backward",
            )
        else:
            gui.absolute_current_image_path = Path(
                current_path.resolve().parent / all_files[idx + 1]
            )
            load_image_from_path(gui, Path(gui.absolute_current_image_path))


def prev_image(gui: AnnotationGUI) -> None:
    if gui.json_path is not None and gui.images:
        if gui.current_image_index <= 0:
            messagebox.showwarning(
                "Beginning of List", "You are at the first image in the JSON."
            )
            return

        if not gui._maybe_save_before_destructive_action("switch images"):
            return

        gui._navigation_in_progress = True
        gui._suspend_image_tree_select = True
        try:
            gui.current_image_index -= 1
            load_image_from_path(gui, gui.images[gui.current_image_index])
        finally:
            gui._navigation_in_progress = False
            gui._suspend_image_tree_select = False
        return

    gui.save_annotations()

    if gui.queue_mode:
        if gui.queue_index <= 0:
            messagebox.showwarning(
                "Start of Queue",
                "You're at the beginning of the unannotated images.",
            )
            return

        gui.queue_index -= 1
        prev_path = gui.unannotated_queue[gui.queue_index]
        gui.absolute_current_image_path = prev_path
        load_image_from_path(gui, prev_path)
        gui._update_queue_status()

    elif gui.check_csv_mode:
        if gui.csv_index <= 0:
            return
        gui.csv_index -= 1
        prev_path = gui.csv_path_queue[gui.csv_index]
        gui.absolute_current_image_path = prev_path
        load_image_from_path(gui, Path(prev_path))
        gui._update_queue_status()
    else:
        idx, all_files = gui._get_image_index_from_directory()
        current_path = gui.absolute_current_image_path
        if current_path is None or not all_files:
            return
        if idx == 0:
            messagebox.showwarning(
                "Beginning of Directory",
                "You've reached the beginning of the current image directory, please use 'Load Image' to find a new image, or use 'Next Image' to move forward",
            )
        else:
            gui.absolute_current_image_path = Path(
                current_path.resolve().parent / all_files[idx - 1]
            )
            load_image_from_path(gui, Path(gui.absolute_current_image_path))


def refresh_image_listbox(gui: AnnotationGUI) -> None:
    if gui.image_tree is None:
        return

    gui._suspend_image_tree_select = True
    try:
        for item in gui.image_tree.get_children():
            gui.image_tree.delete(item)

        for idx, path in enumerate(gui.images):
            progress = gui._image_progress_text(path)
            gui.image_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(extract_filename(path), progress),
                tags=("done",) if gui._image_progress_done(path) else (),
            )

        gui.image_tree.tag_configure("done", foreground="green")

        if 0 <= gui.current_image_index < len(gui.images):
            iid = str(gui.current_image_index)
            if gui.image_tree.exists(iid):
                gui.image_tree.selection_set(iid)
                gui.image_tree.focus(iid)
                gui.image_tree.see(iid)
        else:
            gui.image_tree.selection_remove(gui.image_tree.selection())
    finally:
        if not getattr(gui, "_navigation_in_progress", False):
            gui._suspend_image_tree_select = False


def on_image_list_select(gui: AnnotationGUI, _event=None) -> None:
    if gui.image_tree is None or getattr(gui, "_suspend_image_tree_select", False):
        return

    selection = gui.image_tree.selection()
    if not selection:
        return

    idx = int(selection[0])
    if idx == gui.current_image_index or not (0 <= idx < len(gui.images)):
        return

    gui._navigation_in_progress = True
    gui._suspend_image_tree_select = True
    try:
        if not gui._maybe_save_before_destructive_action("switch images"):
            refresh_image_listbox(gui)
            return

        gui.current_image_index = idx
        load_image_from_path(gui, gui.images[idx])
    finally:
        gui._navigation_in_progress = False
        gui._suspend_image_tree_select = False


def find_unannotated_images(gui: AnnotationGUI) -> None:
    """Scan directory for images not in CSV, enter queue mode."""
    if not hasattr(gui, "abs_csv_path") or not gui.abs_csv_path:
        messagebox.showwarning(
            "No CSV", "Please load a CSV file first (Load CSV button)"
        )
        return

    scan_dir = filedialog.askdirectory(
        initialdir=BASE_DIR, title="Select folder to scan for unannotated images"
    )

    if not scan_dir:
        return

    scan_path = Path(scan_dir)

    try:
        df = pd.read_csv(gui.abs_csv_path)
        col = gui._detect_path_column(df)

        annotated_filenames: set[str] = set()

        for _, row in df.iterrows():
            filename = extract_filename(row[col])

            has_landmarks = any(
                pd.notna(row.get(lm)) and str(row.get(lm, "")).strip()
                for lm in gui.landmarks
            )

            quality = row.get("image_quality", 0)
            try:
                quality = int(quality)
            except (ValueError, TypeError):
                quality = 0

            if has_landmarks or quality != 0:
                annotated_filenames.add(filename)

    except Exception as e:
        messagebox.showerror("CSV Error", f"Failed to read CSV:\n{e}")
        return

    all_images = []
    for dirpath, dirnames, filenames in scan_path.walk():
        if "duplicates" in dirnames:
            dirnames.remove("duplicates")
        for file in filenames:
            if Path(file).suffix.lower() in gui.possible_image_suffix:
                all_images.append(dirpath / file)
                pass
            pass
        pass

    unannotated = [
        img
        for img in all_images
        if (img.name.lower() not in annotated_filenames)
        and (img.parent.name != "duplicates")
    ]

    if not unannotated:
        messagebox.showinfo(
            "All Done!", f"All images in {scan_path.name} are already annotated!"
        )
        return

    unannotated.sort()

    gui.unannotated_queue = unannotated
    gui.queue_index = 0
    gui.queue_mode = True

    gui.absolute_current_image_path = unannotated[0]
    load_image_from_path(gui, unannotated[0])

    gui._update_queue_status()

    messagebox.showinfo(
        "Queue Mode",
        f"Found {len(unannotated)} unannotated images.\n\n"
        f"Use Next/Prev (or N/B keys) to cycle through them.\n"
        f"Click 'Exit Queue Mode' to return to normal browsing.",
    )
    gui.exit_queue_btn.config(state="normal")
    return


def exit_queue_mode(gui: AnnotationGUI) -> None:
    """Return to normal directory browsing."""
    gui.queue_mode = False
    gui.unannotated_queue.clear()
    gui.queue_index = 0
    gui._update_queue_status()
    gui.exit_queue_btn.config(state="disabled")
    messagebox.showinfo("Queue Mode", "Returned to normal directory browsing.")


def check_csv_images(gui: AnnotationGUI):
    gui.abs_csv_path = filedialog.askopenfilename(
        initialdir=BASE_DIR / "data/csv", filetypes=[("CSV File", ("*.csv"))]
    )
    if gui.abs_csv_path:
        df: pd.DataFrame = pd.read_csv(gui.abs_csv_path)
        csv_path_column = gui._detect_path_column(df)
        gui.load_landmarks_from_csv(gui.abs_csv_path)
        gui.check_csv_mode = True
        if gui.csv_local_image_directory_path == None:
            gui.csv_local_image_directory_path = filedialog.askdirectory()
        gui.csv_path_queue = gui._get_csv_images_from_directory(
            Path(gui.csv_local_image_directory_path)
        )
        if len(gui.csv_path_queue) == 0:
            gui.csv_local_image_directory_path = filedialog.askdirectory()

        gui.csv_path_queue = gui._get_csv_images_from_directory(
            Path(gui.csv_local_image_directory_path)
        )

        gui.absolute_current_image_path = Path(gui.csv_path_queue[0])
        load_image_from_path(gui, gui.absolute_current_image_path)
        gui._update_queue_status()

        _ = csv_path_column

    return


def exit_csv_check_mode(gui: AnnotationGUI):
    gui.check_csv_mode = False
    gui.csv_path_queue.clear()
    gui.csv_index = 0
    gui.exit_csv_check_btn.config(state="disabled")
    gui._update_queue_status()

    return


def resolve_image_path(gui: AnnotationGUI, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    if gui.json_dir is not None:
        standard = (gui.json_dir / path).resolve()
        if standard.exists():
            return standard
        # Fallback: if the JSON lives inside the directory referenced by
        # the first component of image_path, strip that component.
        # e.g. image_path="group1/img.tif", json is in .../group1/
        #   → standard tries .../group1/group1/img.tif (wrong)
        #   → fallback strips "group1/" → .../group1/img.tif (correct)
        parts = path.parts
        if len(parts) > 1 and parts[0] == gui.json_dir.name:
            return (gui.json_dir / Path(*parts[1:])).resolve()
        return standard
    return path.resolve()


def get_current_image_record(gui: AnnotationGUI):
    if gui.current_image_path is None:
        return None
    idx = gui.image_index_map.get(gui._path_key(gui.current_image_path))
    if idx is None:
        return None
    images = gui.json_data.get("images", [])
    if not isinstance(images, list) or idx >= len(images):
        return None
    record = images[idx]
    return record if isinstance(record, dict) else None


def sync_current_state_to_json_record(gui: AnnotationGUI) -> None:
    record = gui._get_current_image_record()
    if record is None or gui.current_image_path is None:
        return

    record["image_flag"] = bool(gui.current_image_flag)
    record["image_direction"] = gui.current_image_direction
    record["view"] = gui.current_view_var.get().strip() or None
    record["annotations"] = gui._prepare_landmark_data(for_json=True)

    key = gui._path_key(gui.current_image_path)
    record["resolved_image_path"] = key
    gui.annotations[key] = gui._parse_annotations_for_record(record)


def set_current_view(gui: AnnotationGUI, view_name: str) -> None:
    record = gui._get_current_image_record()
    if record is None:
        return
    record["view"] = view_name
    gui.current_view_var.set(view_name)
    gui._prune_annotations_for_current_view()
    gui._rebuild_landmark_panel_for_view()
    gui._load_note_for_selected_landmark()
    gui.dirty = True
    gui._refresh_image_listbox()


def prune_annotations_for_current_view(gui: AnnotationGUI) -> None:
    if gui.current_image_path is None:
        return

    allowed = gui._get_allowed_landmarks_for_current_view()
    key = gui._path_key(gui.current_image_path)
    pts = gui.annotations.setdefault(key, {})
    meta = gui.landmark_meta.setdefault(key, {})

    to_delete = [lm for lm in pts if lm not in allowed]
    for lm in to_delete:
        del pts[lm]
        meta.pop(lm, None)


def rebuild_landmark_panel_for_view(gui: AnnotationGUI) -> None:
    allowed = gui._get_allowed_landmarks_for_current_view()
    current = gui.selected_landmark.get()

    gui._build_landmark_panel()

    if current in allowed:
        gui.selected_landmark.set(current)
    elif gui.landmarks:
        for lm in gui.landmarks:
            if lm in allowed:
                gui.selected_landmark.set(lm)
                break
        else:
            gui.selected_landmark.set("")
    else:
        gui.selected_landmark.set("")

    gui._draw_points()


def prompt_for_view_if_needed(gui: AnnotationGUI) -> None:
    if gui.current_image_path is None:
        return

    current_view = gui._get_current_view()
    if current_view in gui.allowed_views:
        gui.current_view_var.set(current_view)
        gui._prune_annotations_for_current_view()
        gui._rebuild_landmark_panel_for_view()
        return

    if not gui.allowed_views:
        return

    popup = tk.Toplevel(gui)
    popup.title("Select View")
    popup.transient(gui)
    popup.resizable(False, False)

    frame = ttk.Frame(popup, padding=12)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="This image needs a valid view selection.",
        font=gui.dialogue_font,
    ).pack(anchor="w", pady=(0, 8))

    view_names = list(gui.allowed_views.keys())
    choice_var = tk.StringVar(value=view_names[0])

    combo = ttk.Combobox(
        frame,
        textvariable=choice_var,
        values=view_names,
        state="readonly",
        font=gui.dialogue_font,
        width=28,
    )
    combo.pack(fill="x", pady=(0, 10))
    combo.current(0)
    combo.focus_set()

    result = {"done": False}

    def confirm() -> None:
        if result["done"]:
            return
        result["done"] = True
        gui._set_current_view(choice_var.get())
        gui.current_view_var.set(choice_var.get())
        popup.destroy()
        gui._maybe_autosave_current_image()

    popup.protocol("WM_DELETE_WINDOW", confirm)

    ttk.Button(frame, text="OK", command=confirm).pack(anchor="e")

    popup.update_idletasks()
    popup.deiconify()
    popup.lift()
    popup.grab_set()
    popup.wait_window()


def on_close(gui: AnnotationGUI) -> None:
    if not gui._maybe_save_before_destructive_action("exit"):
        return
    gui.window_close_flag = True
    if gui._onedrive_backup_timer is not None:
        gui.after_cancel(gui._onedrive_backup_timer)
        gui._onedrive_backup_timer = None
    if gui.json_path is not None and not gui._onedrive_upload_in_flight:
        # Non-daemon thread so Python waits for it during shutdown
        # instead of killing it mid-write (which crashes stdout).
        t = threading.Thread(
            target=gui.onedrive_backup.upload_backup_sync,
            args=(gui.json_path,),
            daemon=False,
        )
        t.start()
        # Give the upload a moment to finish before tearing down Tk.
        # If it takes longer, Python shutdown will still wait for the
        # non-daemon thread — but Tk will already be gone.
        t.join(timeout=2.0)
    if gui.db_path is not None:
        gui._export_db_to_csv()
    gui.destroy()


def count_allowed_landmarks(gui: AnnotationGUI, image_path: Path) -> int:
    key = gui._path_key(image_path)
    idx = gui.image_index_map.get(key)
    if idx is None:
        return 0

    if (
        gui.current_image_path is not None
        and gui._path_key(gui.current_image_path) == key
    ):
        view = gui.current_view_var.get().strip()
    else:
        record = gui.json_data["images"][idx]
        view = record.get("view")

    if not view or view not in gui.allowed_views:
        return 0

    return len(gui.allowed_views.get(view, []))


def count_completed_landmarks(gui: AnnotationGUI, image_path: Path) -> int:
    key = gui._path_key(image_path)
    idx = gui.image_index_map.get(key)
    if idx is None:
        return 0

    is_current_image = (
        gui.current_image_path is not None
        and gui._path_key(gui.current_image_path) == key
    )
    if is_current_image:
        view = gui.current_view_var.get().strip()
        annotations = gui.annotations.get(key, {}) or {}
        allowed = (
            set(gui.allowed_views.get(view, []))
            if view and view in gui.allowed_views
            else set(annotations.keys())
        )
        return sum(1 for lm in allowed if annotations.get(lm) is not None)

    record = gui.json_data["images"][idx]
    view = record.get("view")
    annotations = record.get("annotations", {}) or {}

    if view and view in gui.allowed_views:
        allowed = set(gui.allowed_views.get(view, []))
    else:
        allowed = set(annotations.keys())

    done = 0
    for lm in allowed:
        raw = annotations.get(lm)
        if raw is None:
            continue

        if isinstance(raw, dict):
            value = raw.get("value")
        else:
            value = raw

        if value is not None:
            done += 1

    return done


def image_progress_text(gui: AnnotationGUI, image_path: Path) -> str:
    key = gui._path_key(image_path)
    idx = gui.image_index_map.get(key)
    if idx is None:
        return "0/?"

    if (
        gui.current_image_path is not None
        and gui._path_key(gui.current_image_path) == key
    ):
        view = gui.current_view_var.get().strip()
    else:
        record = gui.json_data["images"][idx]
        view = record.get("view")

    done = gui._count_completed_landmarks_for_current_image(image_path)

    if not view or view not in gui.allowed_views:
        return f"{done}/?"

    total = gui._count_allowed_landmarks_for_current_image(image_path)
    return f"{done}/{total}"


def image_progress_done(gui: AnnotationGUI, image_path: Path) -> bool:
    key = gui._path_key(image_path)
    idx = gui.image_index_map.get(key)
    if idx is None:
        return False

    if (
        gui.current_image_path is not None
        and gui._path_key(gui.current_image_path) == key
    ):
        view = gui.current_view_var.get().strip()
    else:
        record = gui.json_data["images"][idx]
        view = record.get("view")

    if not view or view not in gui.allowed_views:
        return False

    done = gui._count_completed_landmarks_for_current_image(image_path)
    total = gui._count_allowed_landmarks_for_current_image(image_path)
    return total > 0 and done >= total


def get_csv_images_from_directory(gui: AnnotationGUI, dir: Path) -> list[Path]:
    try:
        _ = pd.read_csv(gui.abs_csv_path)
    except Exception:
        return []

    try:
        with sqlite3.connect(str(gui.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT image_filename FROM annotations WHERE verified = 0")
            rows: list[tuple[str]] = cursor.fetchall()
    except sqlite3.Error:
        return []

    csv_files = [str(elem[0]) for elem in rows if elem is not None]

    local_dir_csv_files = []
    for root, _dirs, files in dir.walk():
        for file in files:
            if file in csv_files:
                local_dir_csv_files.append(Path(root / file))

    return local_dir_csv_files


def update_queue_status(gui: AnnotationGUI) -> None:
    """Update the queue status label."""
    if gui.queue_mode and gui.unannotated_queue:
        gui.queue_status_var.set(
            f"Queue: {gui.queue_index + 1} / {len(gui.unannotated_queue)} unannotated"
        )
    elif gui.check_csv_mode and gui.csv_path_queue:
        gui.queue_status_var.set(
            f"Queue: {gui.csv_index + 1} / {len(gui.csv_path_queue)} remaining"
        )
    else:
        gui.queue_status_var.set("")
