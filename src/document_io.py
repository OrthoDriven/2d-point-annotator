"""Document I/O — save, load, export, backup operations."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedImport=false, reportDeprecated=false, reportUnusedCallResult=false, reportMissingTypeArgument=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnnecessaryComparison=false, reportOperatorIssue=false, reportImplicitStringConcatenation=false, reportUnnecessaryIsInstance=false, reportImportCycles=false

import ast
import json
import logging
import sqlite3
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path, PurePath
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, Union, cast

import cv2
import pandas as pd

from dirs import BASE_DIR, PLATFORM  # pyright: ignore[reportImplicitRelativeImport]
from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)


AnnotationPoint = Tuple[float, float]
AnnotationValue = Union[AnnotationPoint, List[AnnotationPoint]]


def save_json_file(gui: AnnotationGUI, show_success: bool = False) -> bool:
    if gui.json_path is None:
        messagebox.showwarning("Save", "No JSON data file loaded.")
        return False

    try:
        gui._sync_current_state_to_json_record()

        images_to_save: List[Dict] = []
        save_data = {
            "app_version": gui._get_app_version(),
            "protocol_version": gui._get_protocol_version(),
            "landmarks": list(gui.json_data.get("landmarks", [])),
            "views": dict(gui.allowed_views),
            "images": images_to_save,
        }

        for record in gui.json_data.get("images", []):
            if not isinstance(record, dict):
                continue
            clean = dict(record)
            clean.pop("resolved_image_path", None)
            images_to_save.append(clean)

        tmp_path = gui.json_path.with_suffix(gui.json_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(save_data, handle, indent=2)
        tmp_path.replace(gui.json_path)

        gui._refresh_saved_snapshot_for_current_image()
        gui.dirty = False
        gui._refresh_image_listbox()
        schedule_onedrive_backup(gui)

        if show_success:
            messagebox.showinfo("Saved", "Annotations saved to JSON.")
        return True
    except Exception as e:
        messagebox.showerror("Save Error", f"Failed to save JSON:\n{e}")
        return False


def save_annotations_flow(gui: AnnotationGUI) -> bool:
    """Save annotations. JSON is primary format; SQLite/CSV kept for backup."""
    if not gui.current_image_path:
        messagebox.showwarning("Save", "No image loaded.")
        return False

    return save_json_file(gui, show_success=(PLATFORM == "Windows"))


def auto_save_to_db(gui: AnnotationGUI) -> bool:
    """
    Auto-save annotations to database immediately after changes.
    Returns True on success, False on failure.
    Silent operation - no user feedback unless error occurs.
    """
    if not gui.current_image_path or gui.db_path is None:
        return False

    try:
        _pts, quality = gui._get_annotations()
        landmark_data = prepare_landmark_data(gui)

        with sqlite3.connect(str(gui.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO annotations (image_filename, image_path, image_quality, data, modified_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(image_filename) DO UPDATE SET
                    image_path    = excluded.image_path,
                    image_quality = excluded.image_quality,
                    data          = excluded.data,
                    modified_at   = CURRENT_TIMESTAMP,
                    verified      = annotations.verified
                """,
                (
                    extract_filename(gui.current_image_path),
                    str(gui.current_image_path),
                    quality,
                    json.dumps(landmark_data),
                ),
            )
            conn.commit()

        gui.dirty = False
        return True

    except sqlite3.Error as e:
        messagebox.showerror(
            "Database Error",
            f"Failed to auto-save annotations:\n{e}\n\nYour changes may not be saved.",
        )
        return False
    except Exception as e:
        messagebox.showerror(
            "Save Error",
            f"Unexpected error while saving:\n{e}\n\nYour changes may not be saved.",
        )
        return False


def schedule_onedrive_backup(gui: AnnotationGUI, delay_ms: int = 5000) -> None:
    if gui._onedrive_backup_timer is not None:
        gui.after_cancel(gui._onedrive_backup_timer)
    gui._onedrive_backup_timer = gui.after(delay_ms, lambda: fire_onedrive_backup(gui))


def fire_onedrive_backup(gui: AnnotationGUI) -> None:
    gui._onedrive_backup_timer = None
    if gui.json_path is None or gui._onedrive_upload_in_flight:
        return
    gui._onedrive_upload_in_flight = True
    backup_to_onedrive(gui, gui.json_path)


def backup_to_onedrive(gui: AnnotationGUI, *paths: Path) -> None:
    files_to_backup = [p for p in paths if p is not None and p.exists()]
    if not files_to_backup:
        return

    def _on_done(success, total):
        gui._onedrive_upload_in_flight = False
        logger.info(f"OneDrive backup: {success}/{total} files uploaded")

    gui.onedrive_backup.backup_multiple(
        files_to_backup,
        callback=_on_done,
    )


def backup_with_progress_dialog(gui: AnnotationGUI, files: list) -> None:
    """
    Show progress dialog while backing up files on close.
    Runs upload in background thread, updates GUI via polling.
    """
    dialog = tk.Toplevel(gui)
    dialog.title("Backing up to OneDrive...")
    dialog.geometry("400x150")
    dialog.resizable(False, False)
    dialog.transient(gui)
    dialog.grab_set()

    dialog.update_idletasks()
    x = gui.winfo_x() + (gui.winfo_width() - 400) // 2
    y = gui.winfo_y() + (gui.winfo_height() - 150) // 2
    dialog.geometry(f"400x150+{x}+{y}")

    dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)

    status_var = tk.StringVar(value="Uploading to OneDrive...")
    status_label = ttk.Label(frame, textvariable=status_var, font=("Helvetica", 12))
    status_label.pack(pady=(0, 15))

    progress = ttk.Progressbar(frame, mode="indeterminate", length=300)
    progress.pack(pady=10)
    progress.start(10)

    file_var = tk.StringVar(value="")
    file_label = ttk.Label(
        frame, textvariable=file_var, font=("Helvetica", 9), foreground="gray"
    )
    file_label.pack(pady=(10, 0))

    upload_state = {"done": False, "success": 0, "total": len(files), "current": ""}

    def do_upload():
        """Run uploads in background thread."""
        for fpath in files:
            if fpath.exists():
                upload_state["current"] = fpath.name
                try:
                    if gui.onedrive_backup.upload_backup_sync(fpath):
                        upload_state["success"] += 1
                except Exception as e:
                    logger.warning(f"OneDrive backup failed for {fpath}: {e}")
        upload_state["done"] = True

    def check_progress():
        """Poll upload state and update GUI."""
        if upload_state["current"]:
            file_var.set(f"Uploading: {upload_state['current']}")

        if upload_state["done"]:
            progress.stop()
            dialog.destroy()
        else:
            dialog.after(100, check_progress)

    upload_thread = threading.Thread(target=do_upload, daemon=True)
    upload_thread.start()

    check_progress()
    gui.wait_window(dialog)


def export_db_to_csv(gui: AnnotationGUI) -> None:
    """Export database to CSV file with atomic write (temp file + rename)."""
    current_time = datetime.now()
    if ((current_time - gui.last_update).total_seconds() > 20) or gui.window_close_flag:
        gui.last_update = datetime.now()

        try:
            with sqlite3.connect(str(gui.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT image_path, image_quality, data FROM annotations"
                )
                rows = cast(
                    list[tuple[object | None, object | None, object | None]],
                    cursor.fetchall(),
                )
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Failed to read annotations from database:\n{e}",
            )
            return

        records = []
        for path, quality, data_json in rows:
            if path is None:
                continue
            if quality is None:
                continue
            if data_json is None:
                continue

            path_str = str(path)

            record = {
                gui.csv_path_column: Path(path_str).resolve(),
                "image_quality": quality,
            }

            try:
                landmark_data = json.loads(str(data_json)) if data_json else {}
            except json.JSONDecodeError:
                landmark_data = {}

            for lm in gui.landmarks:
                if lm in landmark_data and landmark_data[lm]:
                    record[lm] = repr(landmark_data[lm])
                else:
                    record[lm] = ""

            records.append(record)

        df = pd.DataFrame(records)

        cols = [gui.csv_path_column, "image_quality"] + gui.landmarks
        df = df[[c for c in cols if c in df.columns]]

        if gui.abs_csv_path is None:
            return
        csv_path = Path(gui.abs_csv_path)
        if gui.check_csv_mode:
            dir = csv_path.parent
            csv_name = Path(extract_filename(csv_path))
            new_name = csv_name.stem + "_CHECKED.csv"
            csv_path = Path(dir / new_name)

        temp_path = csv_path.with_suffix(".csv.tmp")
        try:
            df.to_csv(str(temp_path), index=False)
            temp_path.replace(csv_path)

            backup_to_onedrive(gui, csv_path)

        except OSError as e:
            messagebox.showerror(
                "CSV Export Error",
                f"Failed to save CSV file:\n{e}\n\nYour data is safe in the database.",
            )
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass


def load_points(gui: AnnotationGUI, show_message: bool = True) -> None:
    if not gui.current_image_path:
        if show_message:
            messagebox.showwarning("Load Points", "No image loaded.")
        return
    if gui.abs_csv_path is None:
        if show_message:
            messagebox.showerror("Load Points", "CSV path is not configured.")
        return
    if not Path(gui.abs_csv_path).exists():
        if show_message:
            messagebox.showerror("Load Points", f"CSV not found: {gui.abs_csv_path}")
        return
    try:
        df = pd.read_csv(gui.abs_csv_path)
    except Exception as e:
        if show_message:
            messagebox.showerror("Load Points", f"Failed to read CSV:\n{e}")
        return
    if df.empty:
        gui.annotations[str(gui.current_image_path)] = {}
        gui._update_found_checks({})
        if show_message:
            messagebox.showinfo("Load Points", "No saved points for this image.")
        return

    df_img_path_col = gui._detect_path_column(df)

    rowdf = df.loc[df[df_img_path_col] == str(gui.current_image_path)]
    if rowdf.empty:
        current_filename = PurePath(gui.current_image_path).name
        found_filename = False
        for name in list(df[df_img_path_col]):
            if current_filename in name:
                rowdf = df.loc[df[df_img_path_col] == name]
                found_filename = True
                break

        if found_filename is False:
            gui.annotations[str(gui.current_image_path)] = {}
            gui._update_found_checks({})
            if show_message:
                messagebox.showinfo("Load Points", "No saved points for this image.")
            return
    row: pd.DataFrame = rowdf.iloc[0]
    pts = {}
    per_img_settings = gui.lm_settings.setdefault(str(gui.current_image_path), {})
    for lm in gui.landmarks:
        val = row.get(lm, "")
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                arr = cast(object, ast.literal_eval(val))
            except Exception:
                continue
            if gui._is_line_landmark(lm):
                line_pts: List[Tuple[float, float]] = []
                if isinstance(arr, (list, tuple)):
                    for point in arr[:2]:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            try:
                                line_pts.append((float(point[0]), float(point[1])))
                            except Exception:
                                continue
                if line_pts:
                    pts[lm] = line_pts
                continue
            try:
                if not isinstance(arr, (list, tuple)) or len(arr) < 2:
                    continue
                x, y = float(arr[0]), float(arr[1])
                pts[lm] = (x, y)
            except Exception:
                continue
            if (
                lm in ("LOB", "ROB")
                and isinstance(arr, (list, tuple))
                and len(arr) >= 8
            ):
                method_code = str(arr[2])
                st = {
                    "method": "Flood Fill"
                    if method_code in ("FF", "Flood Fill")
                    else "Adaptive CC",
                    "sens": int(arr[3]),
                    "edge_lock": int(arr[4]),
                    "edge_width": int(arr[5]),
                    "clahe": int(arr[6]),
                    "grow": int(arr[7]),
                }
                per_img_settings[lm] = st
    gui.annotations[str(gui.current_image_path)] = pts
    try:
        gui.current_image_quality = int(row.get("image_quality", 0))
    except (ValueError, TypeError):
        gui.current_image_quality = 0
    gui._update_found_checks(pts)
    gui._draw_points()
    for lm in ("LOB", "ROB"):
        if lm in pts:
            try:
                point = pts[lm]
                if not (
                    isinstance(point, tuple)
                    and len(point) == 2
                    and all(isinstance(v, (int, float)) for v in point)
                ):
                    raise ValueError("LOB/ROB seed must be a point landmark")
                sx, sy = point
                gui.last_seed[lm] = (int(sx), int(sy))
            except Exception:
                gui.last_seed.pop(lm, None)
            vis_var = gui.landmark_visibility.get(lm)
            if (
                gui.last_seed.get(lm) is not None
                and vis_var is not None
                and vis_var.get()
                and cv2 is not None
            ):
                gui._resegment_for(lm, apply_saved_settings=True)
            else:
                gui._update_overlay_for(lm)
    if show_message:
        messagebox.showinfo("Load Points", "Points loaded from CSV.")
    gui._update_path_var()


def prepare_landmark_data(
    gui: AnnotationGUI, for_json: Optional[bool] = None
) -> Dict[str, AnnotationValue]:
    """Prepare landmark data for JSON or legacy database storage."""
    pts, _quality = gui._get_annotations()
    key = (
        gui._path_key(gui.current_image_path)
        if gui.json_path is not None and gui.current_image_path is not None
        else str(gui.current_image_path)
    )
    per_img_settings = gui.lm_settings.get(key, {})
    per_img_meta = gui.landmark_meta.get(key, {})
    use_json_format = gui.json_path is not None if for_json is None else for_json

    landmark_data = {}
    all_landmarks = set(pts.keys()) | set(per_img_meta.keys())

    for lm in gui.landmarks:
        if use_json_format and lm not in all_landmarks:
            continue
        if not use_json_format and lm not in pts:
            continue

        meta = per_img_meta.get(lm, {})
        is_flagged = bool(meta.get("flag", False))
        note = str(meta.get("note", ""))

        value = None
        if lm in pts:
            if gui._is_line_landmark(lm):
                line_pts = gui._get_line_points(lm)
                if line_pts:
                    value = [[float(x), float(y)] for x, y in line_pts]
            else:
                point = pts[lm]
                if not (
                    isinstance(point, tuple)
                    and len(point) == 2
                    and all(isinstance(v, (int, float)) for v in point)
                ):
                    continue

                x, y = point
                if lm in ("LOB", "ROB"):
                    st = per_img_settings.get(lm, gui._current_settings_dict())
                    method_code = "FF" if st["method"] == "Flood Fill" else "ACC"
                    value = [
                        float(x),
                        float(y),
                        method_code,
                        int(st["sens"]),
                        int(st["edge_lock"]),
                        int(st["edge_width"]),
                        int(st["clahe"]),
                        int(st["grow"]),
                    ]
                else:
                    value = [float(x), float(y)]

        if use_json_format:
            if value is None and not is_flagged and not note.strip():
                continue
            landmark_data[lm] = {
                "value": value,
                "flag": is_flagged,
                "note": note,
            }
        elif value is not None:
            landmark_data[lm] = value

    return landmark_data


def import_csv_to_db(gui: AnnotationGUI) -> None:
    try:
        df = pd.read_csv(gui.abs_csv_path)
    except Exception as e:
        messagebox.showerror(
            "CSV Error",
            f"Failed to read CSV file:\n{e}",
        )
        return

    col = gui._detect_path_column(df)

    try:
        with sqlite3.connect(str(gui.db_path)) as conn:
            cursor = conn.cursor()

            for _, row in df.iterrows():
                path = str(row[col])
                try:
                    quality = int(row.get("image_quality", 0))
                except (ValueError, TypeError):
                    quality = 0
                landmark_data = {}

                for lm in gui.landmarks:
                    val = row.get(lm, "")
                    if pd.isna(val) or not str(val).strip():
                        continue

                    try:
                        parsed = cast(object, ast.literal_eval(str(val)))
                        landmark_data[lm] = parsed
                    except (ValueError, SyntaxError):
                        continue

                cursor.execute(
                    """
                    INSERT INTO annotations (image_filename, image_path, image_quality, data)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(image_filename) DO UPDATE SET
                        image_path    = excluded.image_path,
                        image_quality = excluded.image_quality,
                        data          = excluded.data,
                        modified_at   = CURRENT_TIMESTAMP,
                        verified      = annotations.verified
                    """,
                    (
                        extract_filename(path),
                        path,
                        quality,
                        json.dumps(landmark_data),
                    ),
                )
            conn.commit()
    except sqlite3.Error as e:
        messagebox.showerror(
            "Database Error",
            f"Failed to import CSV data to database:\n{e}",
        )


def maybe_save_before_destructive_action(
    gui: AnnotationGUI, why: str = "continue"
) -> bool:
    if not gui.current_image_path:
        return True

    has_unsaved_changes = (
        gui._current_image_has_unsaved_changes()
        if gui.json_path is not None and gui._get_current_image_record() is not None
        else gui.dirty
    )

    if not has_unsaved_changes:
        return True

    should_save = messagebox.askyesno(
        "Unsaved annotations",
        "You have unsaved annotation changes for this image.\n"
        f"Do you want to save before you {why}?",
    )
    if should_save:
        return save_annotations_flow(gui)

    return True


def load_landmarks_from_csv(
    gui: AnnotationGUI, path: Optional[Union[Path, str]] = None
) -> None:
    if path is None:
        if not gui._maybe_save_before_destructive_action("load point name CSV"):
            return
        gui.abs_csv_path = filedialog.askopenfilename(
            initialdir=BASE_DIR, filetypes=[("CSV File", ("*.csv"))]
        )
    else:
        gui.abs_csv_path = str(path)

    gui.json_path = None
    gui.json_dir = None
    gui.json_data = {"landmarks": [], "views": {}, "images": []}
    gui.allowed_views = {}
    gui.images = []
    gui.image_index_map = {}
    gui.current_image_index = -1
    gui.saved_image_snapshots.clear()
    gui.current_view_var.set("")
    if gui.view_dropdown is not None:
        gui.view_dropdown["values"] = ()
    gui.current_image_flag = False

    isolated_data_path = Path(BASE_DIR.parent / "data")
    db_name = extract_filename(Path(gui.abs_csv_path).with_suffix(".db"))

    gui.db_path = Path(isolated_data_path / db_name)
    gui._init_database()
    df: pd.DataFrame = pd.read_csv(gui.abs_csv_path)

    gui.csv_path_column = gui._detect_path_column(df)

    # Removing columns that we know are not landmarks, the rest are assumed to be landmarks
    df.drop(
        columns=["image_quality", gui.csv_path_column],
        inplace=True,
        errors="ignore",
    )

    gui.landmarks = list(df.columns)
    if gui.landmarks:
        gui.selected_landmark.set(gui.landmarks[0])
    gui._build_landmark_panel()
    gui._import_csv_to_db()


def change_image_quality(gui: AnnotationGUI, quality: int) -> None:
    gui.current_image_quality = quality
    if gui.current_image_path:
        gui.path_var.set(extract_filename(gui.current_image_path))
        gui.quality_var.set(str(gui.current_image_quality))
    gui.dirty = True
    # Auto-save to database immediately after quality change
    gui._auto_save_to_db()
    return


def update_path_var(gui: AnnotationGUI) -> None:
    if gui.current_image_path:
        gui.path_var.set(extract_filename(gui.current_image_path))
        gui.quality_var.set(str(gui.current_image_quality))
    gui.dirty = True


def canonical_image_state_for_path(gui: AnnotationGUI, img_path: Path) -> str:
    key = gui._path_key(img_path)
    idx = gui.image_index_map.get(key)
    if idx is None:
        return ""

    record = gui.json_data["images"][idx]
    state = {
        "image_path": record.get("image_path"),
        "image_flag": bool(record.get("image_flag", False)),
        "view": record.get("view"),
        "annotations": record.get("annotations", {}) or {},
    }
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def current_image_state_string(gui: AnnotationGUI) -> str:
    if gui.current_image_path is None:
        return ""

    record = gui._get_current_image_record()
    state = {
        "image_path": record.get("image_path")
        if record
        else str(gui.current_image_path),
        "image_flag": bool(gui.current_image_flag),
        "view": gui.current_view_var.get().strip() or None,
        "annotations": gui._prepare_landmark_data(for_json=True),
    }
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def refresh_saved_snapshot(gui: AnnotationGUI) -> None:
    if gui.current_image_path is None:
        return
    gui.saved_image_snapshots[gui._path_key(gui.current_image_path)] = (
        gui._canonical_image_state_for_path(gui.current_image_path)
    )


def current_image_has_unsaved_changes(gui: AnnotationGUI) -> bool:
    if gui.current_image_path is None:
        return False

    key = gui._path_key(gui.current_image_path)
    current_state = gui._current_image_state_string()
    saved_state = gui.saved_image_snapshots.get(key)
    if saved_state is None:
        saved_state = gui._canonical_image_state_for_path(gui.current_image_path)
        gui.saved_image_snapshots[key] = saved_state
    return current_state != saved_state


def maybe_autosave_current_image(gui: AnnotationGUI) -> bool:
    gui.dirty = True
    gui._refresh_image_listbox()

    autosave_var = getattr(gui, "autosave_var", None)
    autosave_getter = cast(
        Optional[Callable[[], object]], getattr(autosave_var, "get", None)
    )
    if autosave_getter is not None and bool(autosave_getter()):
        ok = gui._save_json_file(show_success=False)
        if ok:
            gui.dirty = False
        return ok

    return True


def init_onedrive_credentials(gui: AnnotationGUI) -> None:
    """
    Initialize OneDrive credentials at app startup.

    If credentials don't exist, this will trigger the auth dialog.
    Runs in background thread to not block GUI startup.
    """

    def _init():
        try:
            gui.onedrive_backup._ensure_initialized()
            logger.info("OneDrive credentials initialized")
        except Exception as e:
            logger.warning(f"OneDrive initialization failed: {e}")

    thread = threading.Thread(target=_init, daemon=True)
    thread.start()


def get_annotations(gui: AnnotationGUI) -> Tuple[Dict[str, AnnotationValue], int]:
    """Returns (points_dict, quality) for current image."""
    if gui.current_image_path is not None:
        current_filename = PurePath(gui.current_image_path).name
        keys_to_try = [str(gui.current_image_path)]
        if gui.json_path is not None:
            keys_to_try.insert(0, gui._path_key(gui.current_image_path))

        for key in keys_to_try:
            if key in gui.annotations:
                quality = gui.current_image_quality
                return gui.annotations[key], quality

        # Fallback: match by filename
        for key in gui.annotations.keys():
            if current_filename in key:
                quality = gui.current_image_quality
                return gui.annotations[key], quality

    return {}, 0


def current_settings_dict(gui: AnnotationGUI) -> Dict:
    return {
        "method": gui.method.get(),
        "sens": int(gui.fill_sensitivity.get()),
        "edge_lock": 1 if gui.edge_lock.get() else 0,
        "edge_width": int(gui.edge_lock_width.get()),
        "clahe": 1 if gui.use_clahe.get() else 0,
        "grow": int(gui.grow_shrink.get()),
    }


def store_current_settings_for(gui: AnnotationGUI, lm: str) -> None:
    per_img = gui.lm_settings.setdefault(str(gui.current_image_path), {})
    per_img[lm] = gui._current_settings_dict()


def apply_settings_to_ui_for(gui: AnnotationGUI, lm: str) -> None:
    st = gui.lm_settings.get(str(gui.current_image_path), {}).get(lm)
    if not st:
        return
    gui.method.set(st["method"])
    try:
        gui.fill_sensitivity.set(int(st["sens"]))
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to apply sensitivity setting for {lm}: {e}")
    try:
        gui.edge_lock.set(bool(int(st["edge_lock"])))
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to apply edge_lock setting for {lm}: {e}")
    try:
        gui.edge_lock_width.set(int(st["edge_width"]))
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to apply edge_width setting for {lm}: {e}")
    try:
        gui.use_clahe.set(bool(int(st["clahe"])))
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to apply clahe setting for {lm}: {e}")
    try:
        gui.grow_shrink.set(int(st["grow"]))
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to apply grow setting for {lm}: {e}")
