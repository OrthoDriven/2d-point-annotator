from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingTypeArgument=false, reportUninitializedInstanceVariable=false, reportOperatorIssue=false
import ast
import datetime
import json
import logging
import sqlite3
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path, PurePath
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Set, Tuple, Union

# Configure logging - writes to file for debugging without disrupting users
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "annotator.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageTk

from auth import OneDriveBackup  # pyright: ignore[reportImplicitRelativeImport]
from dataset_config import load_datasets_config, get_data_dir, get_dataset_dest  # pyright: ignore[reportImplicitRelativeImport]
from downloader import download_dataset  # pyright: ignore[reportImplicitRelativeImport]
from dirs import BASE_DIR, PLATFORM  # pyright: ignore[reportImplicitRelativeImport]
from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]
from landmark_reference import LandmarkReference  # pyright: ignore[reportImplicitRelativeImport]
from landmark_reference_dialog import LandmarkReferenceDialog  # pyright: ignore[reportImplicitRelativeImport]

AnnotationPoint = Tuple[float, float]
AnnotationValue = Union[AnnotationPoint, List[AnnotationPoint]]


class AnnotationGUI(tk.Tk):
    # Initializes the main GUI, state, and loads landmarks from CSV.

    def __init__(self) -> None:
        super().__init__()
        self.tk.call("tk", "scaling", 1.25)

        # Force Tk named fonts (for classic tk widgets)
        import tkinter.font as tkfont

        self.heading_font = tkfont.nametofont("TkDefaultFont").copy()
        self.heading_font.configure(weight="bold")  # keep size default

        self.dialogue_font = tkfont.nametofont("TkDefaultFont").copy()
        self.landmark_font = tkfont.nametofont("TkDefaultFont").copy()
        self.window_close_flag = False
        self._onedrive_backup_timer: str | None = None
        self._onedrive_upload_in_flight: bool = False
        if PLATFORM == "Linux":
            self._configure_linux_fonts()

        self.title("2D Point Annotation")
        self.possible_image_suffix = [
            ".png",
            ".PNG",
            ".jpg",
            ".jpeg",
            ".JPEG",
            ".JPG",
            ".bmp",
            ".BMP",
            ".tif",
            ".tiff",
            ".TIFF",
            ".TIF",
        ]
        self._start_min_w = 0
        self._start_min_h = 0
        self.use_ff = tk.BooleanVar(value=True)
        self.use_adap_cc = tk.BooleanVar(value=False)
        self.autosave_var = tk.BooleanVar(value=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.csv_path_column = "image_path"
        self.dirty = False
        self.path_var = tk.StringVar(value="No image loaded")
        self.quality_var = tk.StringVar(value="N/A")
        self.selected_landmark = tk.StringVar(value="")
        self._landmark_ref: LandmarkReference | None = None
        self._landmark_ref_dialog: LandmarkReferenceDialog | None = None
        _lm_json = Path(__file__).parent.parent / "docs" / "landmarks.json"
        if _lm_json.exists():
            try:
                self._landmark_ref = LandmarkReference(_lm_json)
            except Exception:
                logger.warning(
                    "Failed to load landmark reference: %s", _lm_json, exc_info=True
                )
        self.current_view_var = tk.StringVar(value="")
        self.view_dropdown: ttk.Combobox | None = None
        self.image_flag_var = tk.BooleanVar(value=False)
        self.landmark_visibility: Dict[str, tk.BooleanVar] = {}
        self.landmark_found = {}
        self.landmark_flagged: Dict[str, tk.BooleanVar] = {}
        self.landmark_flag_widgets: Dict[str, tk.Checkbutton] = {}
        self.landmark_found_widgets: Dict[str, tk.Checkbutton] = {}
        self.annotations: Dict[str, Dict[str, AnnotationValue]] = {}
        self.landmarks: List[str] = []
        self.images: List[Path] = []
        self.image_index_map: Dict[str, int] = {}
        self.current_image_index: int = -1
        self.json_path: Optional[Path] = None
        self.json_dir: Optional[Path] = None
        self.json_data: Dict = {"landmarks": [], "views": {}, "images": []}
        self.allowed_views: Dict[str, List[str]] = {}
        self.landmark_meta: Dict[str, Dict[str, Dict[str, Union[bool, str]]]] = {}
        self.saved_image_snapshots: Dict[str, str] = {}
        self.image_tree: ttk.Treeview | None = None
        self._suspend_image_tree_select = False
        self._navigation_in_progress = False
        self.current_image_flag = False
        self.image_flag_check: tk.Checkbutton | None = None
        self.current_image_direction: str = "AP"
        self.image_direction_var = tk.StringVar(value="AP")
        self.line_landmarks: Set[str] = {"L-FA", "R-FA"}
        self.current_image: Image.Image | None = None
        self.current_image_path: Path | None = None
        self.current_image_quality: int = 0
        self.img_obj: ImageTk.PhotoImage | None = None
        self.seg_img_objs: Dict[str, ImageTk.PhotoImage] = {}
        self.seg_item_ids: Dict[str, int] = {}
        self.seg_masks: Dict[str, Dict[str, np.ndarray]] = {}
        self.pair_line_ids: Dict[str, int] = {}
        self.last_seed: Dict[str, Optional[Tuple[int, int]]] = {}
        self.hover_enabled = tk.BooleanVar(value=False)
        self.hover_radius = tk.IntVar(value=25)
        self.hover_circle_id: Optional[int] = None
        self.femoral_axis_enabled = tk.BooleanVar(value=False)
        self.femoral_axis_count = tk.IntVar(value=5)
        self.femoral_axis_proj_length = tk.IntVar(value=60)
        self.femoral_axis_whisker_tip_length = tk.IntVar(value=10)
        self.femoral_axis_item_ids: list[int] = []
        self.extended_crosshair_enabled = tk.BooleanVar(value=False)
        self.extended_crosshair_length = tk.IntVar(value=50)
        self.extended_crosshair_ids: list[int] = []
        self.method = tk.StringVar(value="Flood Fill")
        self.fill_sensitivity = tk.IntVar(value=18)
        self.edge_lock = tk.BooleanVar(value=True)
        self.edge_lock_width = tk.IntVar(value=2)
        self.use_clahe = tk.BooleanVar(value=True)
        self.grow_shrink = tk.IntVar(value=0)
        self.disp_scale: float = 1.0
        self.disp_off: Tuple[int, int] = (0, 0)  # (offset_x, offset_y)
        self.disp_size: Tuple[int, int] = (0, 0)  # (disp_w, disp_h)
        self.base_img_item: Optional[int] = None
        self.mouse_crosshair_ids: list[int] = []
        self.last_mouse_canvas_pos: tuple[int, int] | None = None
        self.right_mouse_held: bool = False
        self.zoom_canvas: tk.Canvas | None = None
        self.zoom_percent = tk.IntVar(value=8)
        self.show_selected_landmark_in_zoom: tk.BooleanVar = tk.BooleanVar(value=True)
        self.zoom_img_obj: ImageTk.PhotoImage | None = None
        self.zoom_base_item: Optional[int] = None
        self.zoom_src_rect: Tuple[float, float, float, float] | None = None
        self.line_preview_id: Optional[int] = None
        self.dragging_landmark: Optional[str] = None
        self.dragging_point_index: Optional[int] = None
        self.dragging_line_whole: bool = False
        self.dragging_line_last_img_pos: Optional[AnnotationPoint] = None
        self.drag_tolerance_px = 10
        self.drag_line_tolerance_px = 8
        self.zoom_crosshair_ids: list[int] = []
        self.zoom_extended_crosshair_ids: list[int] = []
        self.zoom_landmark_overlay_ids: list[int] = []
        self.lm_settings: Dict[str, Dict[str, Dict]] = {}
        self.note_text: Optional[tk.Text] = None
        self.note_text_internal_update: bool = False
        self.csv_loaded = False
        # Also adjust these if you want everything to match:
        # Already configured above to match heading_font
        self._setup_ui()
        self.after(0, self._lock_initial_minsize)
        self.unbind("<Up>")
        self.unbind("<Down>")
        self._bind_shortcut("<Up>", self._on_arrow_up)
        self._bind_shortcut("<Down>", self._on_arrow_down)
        self._bind_shortcut("<f>", self._on_arrow_down)
        self._bind_shortcut("<d>", self._on_arrow_up)
        self._bind_shortcut("<Left>", self._on_arrow_left)
        self._bind_shortcut("<Right>", self._on_arrow_right)
        self._bind_shortcut("<Control-b>", self._on_pg_up)
        self._bind_shortcut("<Control-n>", self._on_pg_down)
        self._bind_shortcut("<n>", self._on_pg_down)
        self._bind_shortcut("<g>", self._on_pg_down)
        self._bind_shortcut("<b>", self._on_pg_up)
        self._bind_shortcut("<BackSpace>", self._on_backspace)
        self._bind_shortcut("<space>", self._on_space)
        self._bind_shortcut("1", self._on_1_press)
        self._bind_shortcut("2", self._on_2_press)
        self._bind_shortcut("3", self._on_3_press)
        self._bind_shortcut("4", self._on_4_press)
        self._bind_shortcut("<h>", self._on_h_press)
        self._bind_shortcut("<question>", self._open_landmark_reference)
        self.queue_mode = False
        self.unannotated_queue: List[Path] = []
        self.queue_index = 0
        self.check_csv_mode = False
        self.csv_path_queue: List[Path] = []
        self.csv_index = 0
        self.db_path: Optional[Path] = None
        self.last_update = datetime.now()
        # Initialize path attributes to prevent AttributeError if accessed before assignment
        self.abs_csv_path: Optional[str] = None
        self.absolute_current_image_path: Optional[Path] = None
        self.csv_local_image_directory_path: Optional[str] = None

        # OneDrive backup integration - initialize early to check/prompt for credentials
        self.onedrive_backup = OneDriveBackup()
        # Trigger credential check at startup (will show auth dialog if needed)
        self.after(100, self._init_onedrive_credentials)

    # Builds the left image canvas, right control panel, and tool widgets.
    def focus_widget(self, event):
        event.widget.focus_set()

    def _on_space(self, event) -> None:
        """
        Here, we are marking the current image as "verified" in the table
        """

        if self.db_path is not None:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    if self.absolute_current_image_path is None:
                        return
                    image_filename = extract_filename(self.absolute_current_image_path)

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
                self._draw_points()
            except sqlite3.Error as e:
                messagebox.showerror(
                    "Database Error",
                    f"Failed to toggle verification status:\n{e}",
                )
        return

    def _is_current_image_verified(self) -> bool:
        if self.db_path is not None:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    if self.absolute_current_image_path is None:
                        return False

                    query = """
                        SELECT verified FROM annotations WHERE image_filename = ?
                    """
                    image_fname = extract_filename(self.absolute_current_image_path)

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

    def _resolve_image_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path.resolve()
        if self.json_dir is not None:
            return (self.json_dir / path).resolve()
        return path.resolve()

    def _path_key(self, path: Union[str, Path]) -> str:
        return str(Path(path).resolve())

    def _get_current_image_record(self) -> Optional[Dict]:
        if self.current_image_path is None:
            return None
        idx = self.image_index_map.get(self._path_key(self.current_image_path))
        if idx is None:
            return None
        images = self.json_data.get("images", [])
        if not isinstance(images, list) or idx >= len(images):
            return None
        record = images[idx]
        return record if isinstance(record, dict) else None

    def _sync_current_state_to_json_record(self) -> None:
        record = self._get_current_image_record()
        if record is None or self.current_image_path is None:
            return

        record["image_flag"] = bool(self.current_image_flag)
        record["image_direction"] = self.current_image_direction
        record["view"] = self.current_view_var.get().strip() or None
        record["annotations"] = self._prepare_landmark_data(for_json=True)

        key = self._path_key(self.current_image_path)
        record["resolved_image_path"] = key
        self.annotations[key] = self._parse_annotations_for_record(record)

    def _get_allowed_landmarks_for_current_view(self) -> set[str]:
        view = self.current_view_var.get().strip()
        if not view:
            return set()
        return set(self.allowed_views.get(view, []))

    def _get_current_view(self) -> str:
        record = self._get_current_image_record()
        if record is None:
            return ""
        val = record.get("view")
        return "" if val is None else str(val)

    def _set_current_view(self, view_name: str) -> None:
        record = self._get_current_image_record()
        if record is None:
            return
        record["view"] = view_name
        self.current_view_var.set(view_name)
        self._prune_annotations_for_current_view()
        self._rebuild_landmark_panel_for_view()
        self._load_note_for_selected_landmark()
        self.dirty = True
        self._refresh_image_listbox()

    def _prune_annotations_for_current_view(self) -> None:
        if self.current_image_path is None:
            return

        allowed = self._get_allowed_landmarks_for_current_view()
        key = self._path_key(self.current_image_path)
        pts = self.annotations.setdefault(key, {})
        meta = self.landmark_meta.setdefault(key, {})

        to_delete = [lm for lm in pts if lm not in allowed]
        for lm in to_delete:
            del pts[lm]
            meta.pop(lm, None)

    def _rebuild_landmark_panel_for_view(self) -> None:
        allowed = self._get_allowed_landmarks_for_current_view()
        current = self.selected_landmark.get()

        self._build_landmark_panel()

        if current in allowed:
            self.selected_landmark.set(current)
        elif self.landmarks:
            for lm in self.landmarks:
                if lm in allowed:
                    self.selected_landmark.set(lm)
                    break
            else:
                self.selected_landmark.set("")
        else:
            self.selected_landmark.set("")

        self._draw_points()

    def _prompt_for_view_if_needed(self) -> None:
        if self.current_image_path is None:
            return

        current_view = self._get_current_view()
        if current_view in self.allowed_views:
            self.current_view_var.set(current_view)
            self._prune_annotations_for_current_view()
            self._rebuild_landmark_panel_for_view()
            return

        if not self.allowed_views:
            return

        popup = tk.Toplevel(self)
        popup.title("Select View")
        popup.transient(self)
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="This image needs a valid view selection.",
            font=self.dialogue_font,
        ).pack(anchor="w", pady=(0, 8))

        view_names = list(self.allowed_views.keys())
        choice_var = tk.StringVar(value=view_names[0])

        combo = ttk.Combobox(
            frame,
            textvariable=choice_var,
            values=view_names,
            state="readonly",
            font=self.dialogue_font,
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
            self._set_current_view(choice_var.get())
            self.current_view_var.set(choice_var.get())
            popup.destroy()
            self._maybe_autosave_current_image()

        popup.protocol("WM_DELETE_WINDOW", confirm)

        ttk.Button(frame, text="OK", command=confirm).pack(anchor="e")

        popup.update_idletasks()
        popup.deiconify()
        popup.lift()
        popup.grab_set()
        popup.wait_window()

    def _on_view_selected(self, _event=None) -> None:
        new_view = self.current_view_var.get().strip()
        if new_view not in self.allowed_views:
            return
        self._set_current_view(new_view)
        self._maybe_autosave_current_image()
        self.focus_set()

    def _on_image_flag_widget_changed(self) -> None:
        self.current_image_flag = bool(self.image_flag_var.get())
        record = self._get_current_image_record()
        if record is not None:
            record["image_flag"] = self.current_image_flag

        self._refresh_image_flag_checkbox_style()

        self.dirty = True
        self._maybe_autosave_current_image()

    def _refresh_image_flag_checkbox_style(self) -> None:
        if self.image_flag_check is None:
            return

        is_flagged = bool(self.image_flag_var.get())

        try:
            self.image_flag_check.configure(
                fg="black",
                activeforeground="black",
                disabledforeground="black",
                selectcolor="#FFB6B6" if is_flagged else self.cget("bg"),
            )
        except Exception:
            pass

    def _on_image_direction_changed(self, _event=None) -> None:
        self.current_image_direction = self.image_direction_var.get()
        record = self._get_current_image_record()
        if record is not None:
            record["image_direction"] = self.current_image_direction
        self._maybe_autosave_current_image()
        self.focus_set()

    def _save_json_file(self, show_success: bool = False) -> bool:
        if self.json_path is None:
            messagebox.showwarning("Save", "No JSON data file loaded.")
            return False

        try:
            self._sync_current_state_to_json_record()

            images_to_save: List[Dict] = []
            save_data = {
                "app_version": self._get_app_version(),
                "protocol_version": self._get_protocol_version(),
                "landmarks": list(self.json_data.get("landmarks", [])),
                "views": dict(self.allowed_views),
                "images": images_to_save,
            }

            for record in self.json_data.get("images", []):
                if not isinstance(record, dict):
                    continue
                clean = dict(record)
                clean.pop("resolved_image_path", None)
                images_to_save.append(clean)

            tmp_path = self.json_path.with_suffix(self.json_path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(save_data, handle, indent=2)
            tmp_path.replace(self.json_path)

            self._refresh_saved_snapshot_for_current_image()
            self.dirty = False
            self._refresh_image_listbox()
            self._schedule_onedrive_backup()

            if show_success:
                messagebox.showinfo("Saved", "Annotations saved to JSON.")
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save JSON:\n{e}")
            return False

    def _parse_annotations_for_record(self, record: Dict) -> Dict[str, AnnotationValue]:
        pts: Dict[str, AnnotationValue] = {}
        annotations = record.get("annotations", {}) or {}
        per_img_settings: Dict[str, Dict] = {}
        per_img_meta: Dict[str, Dict[str, Union[bool, str]]] = {}

        for lm in self.landmarks:
            raw = annotations.get(lm)
            if raw is None:
                continue

            if isinstance(raw, dict):
                val = raw.get("value")
                per_img_meta[lm] = {
                    "flag": bool(raw.get("flag", False)),
                    "note": str(raw.get("note", "")),
                }
            else:
                val = raw
                per_img_meta[lm] = {"flag": False, "note": ""}

            if val is None:
                continue

            if self._is_line_landmark(lm):
                if isinstance(val, list):
                    line_pts: List[Tuple[float, float]] = []
                    for point in val:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            try:
                                line_pts.append((float(point[0]), float(point[1])))
                            except (TypeError, ValueError):
                                continue
                    if line_pts:
                        pts[lm] = line_pts[:2]
                continue

            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    pts[lm] = (float(val[0]), float(val[1]))
                except (TypeError, ValueError):
                    continue

                if lm in ("LOB", "ROB") and len(val) >= 8:
                    method_code = str(val[2])
                    per_img_settings[lm] = {
                        "method": "Flood Fill"
                        if method_code in ("FF", "Flood Fill")
                        else "Adaptive CC",
                        "sens": int(val[3]),
                        "edge_lock": int(val[4]),
                        "edge_width": int(val[5]),
                        "clahe": int(val[6]),
                        "grow": int(val[7]),
                    }

        if self.current_image_path is not None:
            key = self._path_key(self.current_image_path)
            self.lm_settings[key] = per_img_settings
            self.landmark_meta[key] = per_img_meta

        return pts

    def load_data(self) -> None:
        if not self._maybe_save_before_destructive_action("load another data file"):
            return

        json_file = filedialog.askopenfilename(
            initialdir=BASE_DIR,
            filetypes=[("JSON File", "*.json")],
            title="Load annotation data JSON",
        )
        if not json_file:
            return

        try:
            json_path = Path(json_file)
            with json_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as e:
            messagebox.showerror("Load Data", f"Failed to read JSON:\n{e}")
            return

        landmarks = data.get("landmarks")
        views = data.get("views")
        images = data.get("images")

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

        allowed_views: Dict[str, List[str]] = {}
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

        self.json_path = json_path
        self.json_dir = json_path.parent
        self.allowed_views = allowed_views
        self.json_data = {
            "landmarks": list(landmarks),
            "views": dict(self.allowed_views),
            "images": [],
        }
        self.landmarks = list(landmarks)
        self.images = []
        self.image_index_map = {}
        self.current_image_index = -1
        self.saved_image_snapshots = {}
        self.annotations.clear()
        self.lm_settings.clear()
        self.landmark_meta.clear()
        self.seg_masks.clear()
        self.last_seed.clear()
        self.queue_mode = False
        self.check_csv_mode = False
        self.current_view_var.set("")

        if self.view_dropdown is not None:
            self.view_dropdown["values"] = list(self.allowed_views.keys())

        missing: List[str] = []
        for idx, raw_record in enumerate(images):
            if not isinstance(raw_record, dict):
                missing.append(f"images[{idx}] is not an object")
                continue
            if "image_path" not in raw_record:
                missing.append(f"images[{idx}] is missing image_path")
                continue

            resolved = self._resolve_image_path(str(raw_record["image_path"]))
            record = dict(raw_record)
            record.setdefault("image_flag", False)
            record.setdefault("view", None)
            record.setdefault("annotations", {})
            record["resolved_image_path"] = str(resolved)
            self.json_data["images"].append(record)

            if not resolved.exists():
                missing.append(str(resolved))
                continue

            key = self._path_key(resolved)
            self.images.append(resolved)
            self.image_index_map[key] = len(self.json_data["images"]) - 1

        self._build_landmark_panel()

        if missing:
            preview = "\n".join(missing[:15])
            more = "" if len(missing) <= 15 else f"\n... and {len(missing) - 15} more"
            messagebox.showwarning(
                "Missing image paths",
                "Some image paths from the JSON could not be found:\n\n"
                f"{preview}{more}",
            )

        if not self.images:
            self.current_image = None
            self.current_image_path = None
            self.absolute_current_image_path = None
            self.current_image_index = -1
            self.current_image_flag = False
            self.path_var.set("No valid images found in JSON")
            self.quality_var.set("0")
            self.current_view_var.set("")
            self.canvas.delete("all")
            self._render_black_zoom_view()
            self.dirty = False
            self._refresh_image_listbox()
            return

        self.current_image_index = 0
        self.load_image_from_path(self.images[0])

        if self.selected_landmark.get():
            self._on_landmark_selected()

        for image_path in self.images:
            self.saved_image_snapshots[self._path_key(image_path)] = (
                self._canonical_image_state_for_path(image_path)
            )

        self._refresh_image_listbox()

    @staticmethod
    def _get_app_version() -> str:
        import platform as _platform

        if _platform.system() == "Windows":
            try:
                import platformdirs

                state_path = (
                    Path(platformdirs.user_documents_dir())
                    / "2D-Point-Annotator"
                    / "update_state.json"
                )
            except Exception:
                state_path = Path.home() / "2D-Point-Annotator" / "update_state.json"
        else:
            state_path = Path.home() / "2d-point-annotator" / "update_state.json"

        try:
            with state_path.open() as f:
                return json.load(f).get("version", "dev")
        except Exception:
            return "dev"

    @staticmethod
    def _get_protocol_version() -> str:
        path = Path("docs/landmarks.json")
        try:
            with path.open() as f:
                return json.load(f).get("metadata")["version"]
        except:
            return "N/A"

    # -------------------------------------------------------------------------
    # Study-data download helpers
    # -------------------------------------------------------------------------

    def _initial_dl_status(self) -> str:
        if not self._datasets_config.datasets:
            return "No datasets configured."

        name = self._selected_ds_name.get()
        dataset = next(
            (ds for ds in self._datasets_config.datasets if ds.name == name), None
        )
        if not dataset:
            return "Select a dataset."

        dest = get_dataset_dest(dataset)
        if dest.exists() and any(dest.iterdir()):
            return f"Data folder exists: {dataset.subfolder}"
        return f"Will download to: {dataset.subfolder}"

    def _on_download_data(self) -> None:
        name = self._selected_ds_name.get()
        dataset = next(
            (ds for ds in self._datasets_config.datasets if ds.name == name), None
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

        self._dl_button.config(state="disabled")
        self._dl_status_var.set("Starting download…")

        def on_progress(msg: str) -> None:
            self.after(0, lambda m=msg: self._dl_status_var.set(m))

        def on_done(exc: Optional[Exception]) -> None:
            if exc is None:
                self.after(
                    0,
                    lambda: (
                        self._dl_status_var.set(
                            f"Download complete: {dataset.subfolder}"
                        ),
                        self._dl_button.config(state="normal"),
                    ),
                )
            else:
                self.after(
                    0,
                    lambda e=exc: (
                        self._dl_status_var.set(f"Download failed: {e}"),
                        self._dl_button.config(state="normal"),
                        messagebox.showerror(
                            "Download Failed",
                            f"Could not download study data:\n\n{e}",
                        ),
                    ),
                )

        download_dataset(
            dataset=dataset,
            method=self._datasets_config.download_method,
            on_progress=on_progress,
            on_done=on_done,
        )

    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        PANEL_WIDTH = 450
        SCROLLBAR_WIDTH = 18
        IMAGE_LIST_HEIGHT = 180
        CANVAS_HEIGHT = 220

        self.option_add("*Scale.takeFocus", "0")
        self.option_add("*Checkbutton.takeFocus", "0")
        self.option_add("*Button.takeFocus", "0")
        self.option_add("*Entry.takeFocus", "0")
        self.option_add("*TCombobox.takeFocus", "0")

        main = tk.Frame(self)
        main.pack(fill="both", expand=True)

        left_tools = tk.Frame(main, width=PANEL_WIDTH)
        left_tools.pack(side=tk.LEFT, fill="y", padx=(10, 5), pady=10)
        left_tools.pack_propagate(False)
        self._left_tools = left_tools

        self.canvas = tk.Canvas(main, bg="grey", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill="both", expand=True)
        # recompute transform & redraw on canvas size changes
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<ButtonPress-3>", self._on_right_button_press)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_button_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_scroll_linux(1))
        self.canvas.bind("<Button-5>", lambda e: self._on_scroll_linux(-1))

        self.landmark_font = tkfont.Font(
            family="Liberation Sans", size=18, weight="bold"
        )
        self.shadow_font = tkfont.Font(family="Liberation Sans", size=20, weight="bold")

        ctrl = tk.Frame(main, width=PANEL_WIDTH)
        ctrl.pack(side=tk.RIGHT, fill="y", padx=(5, 10), pady=10)
        ctrl.pack_propagate(False)
        self._ctrl = ctrl

        zoom_wrap = ttk.LabelFrame(left_tools, text="Zoom View")
        zoom_wrap.pack(fill="x", pady=(0, 8))
        self.zoom_canvas = tk.Canvas(
            zoom_wrap,
            width=450,
            height=450,
            bg="black",
            highlightthickness=0,
        )
        self.zoom_canvas.pack(fill="x", padx=0, pady=0)
        tk.Scale(
            zoom_wrap,
            from_=2,
            to=40,
            orient="horizontal",
            label="Zoom (x)",
            variable=self.zoom_percent,
            command=self._on_zoom_change,
            font=self.dialogue_font,
        ).pack(fill="x", padx=6, pady=(6, 6))
        tk.Checkbutton(
            zoom_wrap,
            text="Show Selected Landmark",
            variable=self.show_selected_landmark_in_zoom,
            command=self._refresh_zoom_landmark_overlay,
            font=self.dialogue_font,
        ).pack(anchor="w", padx=6, pady=(0, 6))
        self.after(0, self._render_black_zoom_view)

        hover_wrap = ttk.LabelFrame(left_tools, text="Hover Circle Tool")
        hover_wrap.pack(fill="x")
        tk.Checkbutton(
            hover_wrap,
            text="Show Hover Circle",
            variable=self.hover_enabled,
            command=self._toggle_hover,
            font=self.dialogue_font,
        ).pack(anchor="w", padx=6, pady=(6, 0))
        self.radius_scale = tk.Scale(
            hover_wrap,
            from_=1,
            to=300,
            orient="horizontal",
            label="Hover Radius",
            variable=self.hover_radius,
            command=self._on_radius_change,
            font=self.dialogue_font,
        )
        self.radius_scale.config(state="disabled")
        self.radius_scale.pack(fill="x", padx=6, pady=6)

        axis_wrap = ttk.LabelFrame(left_tools, text="Femoral Axis Tool")
        axis_wrap.pack(fill="x", pady=(8, 0))

        tk.Checkbutton(
            axis_wrap,
            text="Show Femoral Axis",
            variable=self.femoral_axis_enabled,
            command=self._toggle_femoral_axis,
            font=self.dialogue_font,
        ).pack(anchor="w", padx=6, pady=(6, 0))

        self.femoral_axis_count_scale = tk.Scale(
            axis_wrap,
            from_=1,
            to=20,
            orient="horizontal",
            label="N Orthogonal Projections",
            variable=self.femoral_axis_count,
            command=self._on_femoral_axis_count_change,
            font=self.dialogue_font,
        )
        self.femoral_axis_count_scale.config(state="disabled")
        self.femoral_axis_count_scale.pack(fill="x", padx=6, pady=(6, 2))

        self.femoral_axis_whisker_tip_length_scale = tk.Scale(
            axis_wrap,
            from_=1,
            to=80,
            orient="horizontal",
            label="Whisker Tip Length",
            variable=self.femoral_axis_whisker_tip_length,
            command=self._on_femoral_axis_whisker_tip_length_change,
            font=self.dialogue_font,
        )
        self.femoral_axis_whisker_tip_length_scale.config(state="disabled")
        self.femoral_axis_whisker_tip_length_scale.pack(fill="x", padx=6, pady=(0, 6))

        cross_wrap = ttk.LabelFrame(left_tools, text="Extended Crosshair Tool")
        cross_wrap.pack(fill="x", pady=(8, 0))

        tk.Checkbutton(
            cross_wrap,
            text="Show Extended Crosshair",
            variable=self.extended_crosshair_enabled,
            command=self._toggle_extended_crosshair,
            font=self.dialogue_font,
        ).pack(anchor="w", padx=6, pady=(6, 0))

        self.crosshair_length_scale = tk.Scale(
            cross_wrap,
            from_=5,
            to=400,
            orient="horizontal",
            label="Crosshair Length",
            variable=self.extended_crosshair_length,
            command=self._on_extended_crosshair_length_change,
            font=self.dialogue_font,
        )
        self.crosshair_length_scale.config(state="disabled")
        self.crosshair_length_scale.pack(fill="x", padx=6, pady=6)

        tk.Label(
            left_tools,
            text=f"App: v{self._get_app_version()}\nProtocol: v{self._get_protocol_version()}\nNOT FDA APPROVED",
            font=self.dialogue_font,
            fg="grey50",
            anchor="w",
            justify="left",
        ).pack(side="bottom", fill="x", padx=6, pady=(0, 4))

        # ── Study data download ──────────────────────────────────────────────
        dl_frame = ttk.LabelFrame(ctrl, text="Study Data")
        dl_frame.pack(fill="x", pady=(0, 8))

        self._datasets_config = load_datasets_config()
        ds_names = [ds.name for ds in self._datasets_config.datasets]

        self._selected_ds_name = tk.StringVar()
        if ds_names:
            self._selected_ds_name.set(ds_names[0])

        self._ds_dropdown = ttk.Combobox(
            dl_frame,
            textvariable=self._selected_ds_name,
            values=ds_names,
            state="readonly",
            font=self.dialogue_font,
        )
        self._ds_dropdown.pack(fill="x", padx=6, pady=(4, 2))
        self._ds_dropdown.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._dl_status_var.set(self._initial_dl_status()),
        )

        self._dl_status_var = tk.StringVar(value=self._initial_dl_status())
        tk.Label(
            dl_frame,
            textvariable=self._dl_status_var,
            font=self.dialogue_font,
            fg="grey40",
            anchor="w",
            wraplength=420,
            justify="left",
        ).pack(fill="x", padx=6, pady=(2, 2))

        self._dl_button = tk.Button(
            dl_frame,
            text="Download",
            command=self._on_download_data,
            font=self.heading_font,
            state="normal" if ds_names else "disabled",
        )
        self._dl_button.pack(fill="x", padx=6, pady=(0, 6))
        # ── End study data download ──────────────────────────────────────────

        tk.Button(
            ctrl, text="Load Data", command=self.load_data, font=self.heading_font
        ).pack(fill="x", pady=5)
        tk.Button(
            ctrl, text="Load Image", command=self.load_image, font=self.heading_font
        ).pack(fill="x", pady=5)
        tk.Button(
            ctrl, text="Next Image", command=self._next_image, font=self.heading_font
        ).pack(fill="x", pady=5)
        tk.Button(
            ctrl,
            text="Previous Image",
            command=self._prev_image,
            font=self.heading_font,
        ).pack(fill="x", pady=5)
        tk.Button(
            ctrl,
            text="Save Annotations",
            command=self.save_annotations,
            font=self.heading_font,
        ).pack(fill="x", pady=5)

        self.autosave_check = tk.Checkbutton(
            ctrl,
            text="Autosave",
            variable=self.autosave_var,
            font=self.dialogue_font,
        )
        self.autosave_check.pack(anchor="w", pady=(0, 6))

        img_frame = ttk.LabelFrame(ctrl, text="Image + Quality")
        img_frame.pack(fill="x", pady=(10, 10))

        row = ttk.Frame(img_frame)
        row.pack(fill="x", padx=6, pady=6)

        row_meta = ttk.Frame(img_frame)
        row_meta.pack(fill="x", padx=6, pady=(0, 6))

        self.image_flag_check = tk.Checkbutton(
            row_meta,
            text="Image Flag",
            variable=self.image_flag_var,
            command=self._on_image_flag_widget_changed,
            font=self.dialogue_font,
            fg="black",
            activeforeground="black",
            disabledforeground="black",
            selectcolor=self.cget("bg"),
        )
        self.image_flag_check.pack(side="left", padx=(0, 12))

        tk.Label(row_meta, text="Dir:", font=self.dialogue_font).pack(
            side="left", padx=(0, 2)
        )
        self.direction_dropdown = ttk.Combobox(
            row_meta,
            textvariable=self.image_direction_var,
            values=["AP", "PA"],
            state="readonly",
            font=self.dialogue_font,
            width=4,
            takefocus=False,
        )
        self.direction_dropdown.pack(side="left")
        self.direction_dropdown.bind(
            "<<ComboboxSelected>>", self._on_image_direction_changed
        )

        row_meta2 = ttk.Frame(img_frame)
        row_meta2.pack(fill="x", padx=6, pady=(0, 6))

        tk.Label(row_meta2, text="View:", font=self.dialogue_font).pack(side="left")
        self.view_dropdown = ttk.Combobox(
            row_meta2,
            textvariable=self.current_view_var,
            state="readonly",
            font=self.dialogue_font,
            width=24,
            takefocus=False,
        )
        self.view_dropdown.pack(side="left", fill="x", expand=True)
        self.view_dropdown.bind("<<ComboboxSelected>>", self._on_view_selected)

        tk.Button(
            ctrl,
            text="Find Unannotated Images",
            command=self._find_unannotated_images,
        ).pack(fill="x", pady=5)

        # Add status label (update the Image frame to show queue status)
        self.queue_status_var = tk.StringVar(value="")
        tk.Label(
            img_frame, textvariable=self.queue_status_var, fg="blue", font="16"
        ).pack(fill="x", padx=6, pady=(0, 6))
        self.exit_queue_btn = tk.Button(
            ctrl,
            text="Exit Queue Mode",
            command=self._exit_queue_mode,
            state="disabled",  # Only enabled when in queue mode
        )
        self.exit_queue_btn.pack(fill="x", pady=5)

        tk.Button(
            ctrl,
            text="Check CSV Images",
            command=self._check_csv_images,
        ).pack(fill="x", pady=5)

        self.exit_csv_check_btn = tk.Button(
            ctrl,
            text="Exit CSV Check Mode",
            command=self._exit_csv_check_mode,
            state="disabled",
        )
        self.exit_csv_check_btn.pack(fill="x", pady=5)

        path_entry = tk.Entry(
            row,
            textvariable=self.path_var,
            state="readonly",
            relief="sunken",
            font=self.dialogue_font,
        )
        path_entry.pack(side="left", fill="x", expand=True)

        quality_entry = tk.Entry(
            row,
            textvariable=self.quality_var,
            state="readonly",
            relief="sunken",
            width=10,
            justify="center",
            font=self.dialogue_font,
        )
        quality_entry.pack(side="right", padx=(6, 0))

        tk.Label(ctrl, text="Images in JSON:", font=self.heading_font).pack(anchor="w")

        image_container = tk.Frame(
            ctrl,
            bd=1,
            relief="sunken",
            width=PANEL_WIDTH,
            height=IMAGE_LIST_HEIGHT,
        )
        image_container.pack(fill="x", pady=(2, 8))
        image_container.pack_propagate(False)

        self.image_tree = ttk.Treeview(
            image_container,
            columns=("image", "progress"),
            show="headings",
            height=8,
        )
        self.image_tree.heading("image", text="Image")
        self.image_tree.heading("progress", text="Done")
        self.image_tree.column("image", width=290, anchor="w")
        self.image_tree.column("progress", width=90, anchor="center")
        self.image_tree.pack(side=tk.LEFT, fill="both", expand=True)

        image_scrollbar = tk.Scrollbar(
            image_container,
            orient="vertical",
            command=self.image_tree.yview,
        )
        image_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.image_tree.configure(yscrollcommand=image_scrollbar.set)

        self.image_tree.bind("<<TreeviewSelect>>", self._on_image_list_select)
        self.image_tree.bind("<Enter>", lambda _e: self._bind_image_list_scroll(True))
        self.image_tree.bind("<Leave>", lambda _e: self._bind_image_list_scroll(False))

        lm_heading_row = tk.Frame(ctrl)
        lm_heading_row.pack(fill="x")
        tk.Label(lm_heading_row, text="Landmarks:", font=self.heading_font).pack(
            side="left"
        )
        if self._landmark_ref is not None:
            tk.Button(
                lm_heading_row,
                text="?",
                command=self._open_landmark_reference,
                font=self.dialogue_font,
                width=2,
                padx=0,
                pady=0,
            ).pack(side="left", padx=(4, 0))
        lp_header = tk.Frame(ctrl)
        lp_header.pack(fill="x", padx=2)
        lp_header.grid_columnconfigure(0, minsize=55)
        lp_header.grid_columnconfigure(1, minsize=140)
        lp_header.grid_columnconfigure(2, minsize=80)
        lp_header.grid_columnconfigure(3, minsize=60)
        tk.Label(lp_header, text="View", anchor="w", font=self.heading_font).grid(
            row=0, column=0, sticky="w", padx=(2, 4)
        )
        tk.Label(lp_header, text="Name", anchor="w", font=self.heading_font).grid(
            row=0, column=1, sticky="w", padx=(2, 4)
        )
        tk.Label(lp_header, text="Ann.", anchor="w", font=self.heading_font).grid(
            row=0, column=2, sticky="w", padx=(2, 4)
        )
        tk.Label(lp_header, text="Flag", anchor="w", font=self.heading_font).grid(
            row=0, column=3, sticky="w", padx=(2, 4)
        )
        self.landmark_panel_container = tk.Frame(
            ctrl, bd=1, relief="sunken", width=PANEL_WIDTH, height=CANVAS_HEIGHT
        )
        self.landmark_panel_container.pack(fill="x", pady=(0, 0))
        self.landmark_panel_container.pack_propagate(False)

        self.lp_canvas = tk.Canvas(
            self.landmark_panel_container,
            height=CANVAS_HEIGHT,
            width=PANEL_WIDTH - SCROLLBAR_WIDTH,
            highlightthickness=0,
        )
        self.lp_canvas.pack(side=tk.LEFT, fill="both")
        self.lp_scrollbar = tk.Scrollbar(
            self.landmark_panel_container,
            orient="vertical",
            command=self.lp_canvas.yview,
        )
        self.lp_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.lp_canvas.configure(yscrollcommand=self.lp_scrollbar.set)
        self.lp_inner = tk.Frame(self.lp_canvas)
        self.lp_canvas.create_window((0, 0), window=self.lp_inner, anchor="nw")
        self.lp_inner.bind(
            "<Configure>",
            lambda e: self.lp_canvas.configure(scrollregion=self.lp_canvas.bbox("all")),
        )
        self.lp_inner.bind("<Enter>", lambda e: self._bind_landmark_scroll(True))
        self.lp_inner.bind("<Leave>", lambda e: self._bind_landmark_scroll(False))
        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=(6, 6))
        buttons_row = tk.Frame(ctrl)
        buttons_row.pack(fill="x", pady=(0, 6))
        tk.Button(
            buttons_row,
            text="View All",
            command=lambda: self._set_all_visibility(True),
            font=self.dialogue_font,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            buttons_row,
            text="View None",
            command=lambda: self._set_all_visibility(False),
            font=self.dialogue_font,
        ).pack(side="left", expand=True, fill="x")

        note_wrap = ttk.LabelFrame(ctrl, text="Landmark Note")
        note_wrap.pack(fill="x", pady=(8, 0))

        self.note_text = tk.Text(
            note_wrap,
            height=8,
            wrap="word",
            font=self.dialogue_font,
        )
        self.note_text.pack(fill="x", padx=6, pady=6)
        self.note_text.bind("<<Modified>>", self._on_note_text_modified)
        self._set_note_editor_enabled(False)

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=(6, 6))
        seg_wrap = ttk.LabelFrame(ctrl, text="Fill Tool (Obturator)")
        seg_wrap.pack(fill="x", pady=(8, 0))
        row1 = tk.Frame(seg_wrap)
        row1.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(row1, text="Method:", font=self.heading_font).pack(side="left")
        # self.fill_box = ttk.Combobox(
        #     row1,
        #     textvariable=self.method,
        #     values=["Flood Fill", "Adaptive CC"],
        #     width=14,
        #     state="readonly",
        # )
        # self.fill_box.pack(side="left", padx=(6, 0))
        # self.fill_box.bind_class("ComboboxListbox", "<KeyRelease>", self.focus_set())
        self.ff_button = tk.Checkbutton(
            row1,
            text="FF",
            variable=self.use_ff,
            font=self.dialogue_font,
            command=self._change_method_to_ff,
        )

        self.ff_button.pack(side="left")
        self.adap_cc_button = tk.Checkbutton(
            row1,
            text="ACC",
            variable=self.use_adap_cc,
            font=self.dialogue_font,
            command=self._change_method_to_acc,
        )
        self.adap_cc_button.pack(side="left")

        tk.Checkbutton(
            row1,
            text="CLAHE",
            variable=self.use_clahe,
            command=lambda: self._resegment_selected_if_needed(),
            font=self.dialogue_font,
        ).pack(side="left", padx=(10, 0))
        tk.Scale(
            seg_wrap,
            from_=1,
            to=50,
            orient="horizontal",
            label="Sensitivity",
            variable=self.fill_sensitivity,
            command=lambda _v: self._resegment_selected_if_needed(),
            font=self.dialogue_font,
        ).pack(fill="x", padx=6, pady=(6, 4))
        tk.Checkbutton(
            seg_wrap,
            text="Edge lock (flood fill)",
            variable=self.edge_lock,
            command=lambda: self._resegment_selected_if_needed(),
            font=self.dialogue_font,
        ).pack(anchor="w", padx=6)
        tk.Scale(
            seg_wrap,
            from_=1,
            to=5,
            orient="horizontal",
            label="Edge lock width",
            variable=self.edge_lock_width,
            command=lambda _v: self._resegment_selected_if_needed(),
            font=self.dialogue_font,
        ).pack(fill="x", padx=6, pady=(2, 6))
        tk.Button(
            seg_wrap,
            text="Re-segment (use current sliders)",
            command=lambda: self._resegment_for(self.selected_landmark.get()),
            font=self.dialogue_font,
        ).pack(fill="x", padx=6, pady=(0, 8))

    def _detect_path_column(self, df: pd.DataFrame) -> str:
        """Detect which column contains image paths."""
        # Try known column names in order of preference
        candidates = ["image_path", "Dataset", "dataset", "path", "file", "filename"]

        for col in candidates:
            if col in df.columns:
                return col

        # Fallback: use first column if none match
        if len(df.columns) > 0:
            return df.columns[0]

        # Last resort default
        return "image_path"

    def _recompute_transform(self) -> None:
        if not self.current_image:
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        iw, ih = self.current_image.size
        scale = min(cw / iw, ch / ih)
        disp_w, disp_h = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        off_x = (cw - disp_w) // 2
        off_y = (ch - disp_h) // 2
        self.disp_scale = scale
        self.disp_off = (off_x, off_y)
        self.disp_size = (disp_w, disp_h)

    def _img_to_screen(self, xi: float, yi: float) -> Tuple[float, float]:
        off_x, off_y = self.disp_off
        s = self.disp_scale
        return off_x + xi * s, off_y + yi * s

    def _screen_to_img(self, xs: float, ys: float) -> Tuple[float, float]:
        off_x, off_y = self.disp_off
        s = self.disp_scale or 1.0
        return (xs - off_x) / s, (ys - off_y) / s

    def _display_rect(self) -> Tuple[int, int, int, int]:
        off_x, off_y = self.disp_off
        disp_w, disp_h = self.disp_size
        return off_x, off_y, off_x + disp_w, off_y + disp_h

    def _get_zoom_canvas_size(self) -> int:
        if self.zoom_canvas is None:
            return 1

        w = self.zoom_canvas.winfo_width()
        h = self.zoom_canvas.winfo_height()

        if w <= 1 or h <= 1:
            req_w = self.zoom_canvas.winfo_reqwidth()
            req_h = self.zoom_canvas.winfo_reqheight()
            w = max(w, req_w, 1)
            h = max(h, req_h, 1)

        return max(1, min(w, h))

    def _render_black_zoom_view(self) -> None:
        if self.zoom_canvas is None:
            return

        size = self._get_zoom_canvas_size()
        black_img = Image.new("RGB", (size, size), "black")
        self.zoom_img_obj = ImageTk.PhotoImage(black_img)

        if self.zoom_base_item is None:
            self.zoom_base_item = self.zoom_canvas.create_image(
                0, 0, anchor="nw", image=self.zoom_img_obj
            )
        else:
            self.zoom_canvas.itemconfigure(self.zoom_base_item, image=self.zoom_img_obj)
            self.zoom_canvas.coords(self.zoom_base_item, 0, 0)

        self.zoom_src_rect = None
        self._update_zoom_crosshair()
        self._clear_zoom_landmark_overlay()

    def _update_zoom_view(
        self, mouse_x: Optional[float] = None, mouse_y: Optional[float] = None
    ) -> None:
        if self.zoom_canvas is None:
            return

        size = self._get_zoom_canvas_size()

        if self.current_image is None or mouse_x is None or mouse_y is None:
            self._render_black_zoom_view()
            return

        x0, y0, x1, y1 = self._display_rect()
        if not (x0 <= mouse_x < x1 and y0 <= mouse_y < y1):
            self._render_black_zoom_view()
            return

        xi, yi = self._screen_to_img(mouse_x, mouse_y)
        iw, ih = self.current_image.size

        if not (0 <= xi < iw and 0 <= yi < ih):
            self._render_black_zoom_view()
            return

        zoom_lev = max(2, min(40, float(self.zoom_percent.get())))
        half_w = max(1.0, iw / (zoom_lev * 2.0))
        half_h = max(1.0, ih / (zoom_lev * 2.0))

        src_left = float(xi) - half_w
        src_top = float(yi) - half_h
        src_right = float(xi) + half_w
        src_bottom = float(yi) + half_h

        self.zoom_src_rect = (src_left, src_top, src_right, src_bottom)

        try:
            out = self.current_image.transform(
                (size, size),
                Image.Transform.EXTENT,
                self.zoom_src_rect,
                resample=Image.Resampling.BICUBIC,
                fill=0,
            )
        except TypeError:
            out = self.current_image.transform(
                (size, size),
                Image.Transform.EXTENT,
                self.zoom_src_rect,
                resample=Image.Resampling.BICUBIC,
            )

        self.zoom_img_obj = ImageTk.PhotoImage(out)

        if self.zoom_base_item is None:
            self.zoom_base_item = self.zoom_canvas.create_image(
                0, 0, anchor="nw", image=self.zoom_img_obj
            )
        else:
            self.zoom_canvas.itemconfigure(self.zoom_base_item, image=self.zoom_img_obj)
            self.zoom_canvas.coords(self.zoom_base_item, 0, 0)

        self._update_zoom_crosshair()
        self._refresh_zoom_landmark_overlay()

    def _on_zoom_change(self, _value) -> None:
        if self.last_mouse_canvas_pos is None:
            self._update_zoom_view(None, None)
            return

        mouse_x, mouse_y = self.last_mouse_canvas_pos
        self._update_zoom_view(mouse_x, mouse_y)

    def _change_zoom_percent(self, delta) -> None:
        new_zoom = max(2, min(40, self.zoom_percent.get() + delta))
        if new_zoom != self.zoom_percent.get():
            self.zoom_percent.set(new_zoom)
            self._on_zoom_change(str(new_zoom))

    def _update_zoom_crosshair(self) -> None:
        if self.zoom_canvas is None:
            return

        size = self._get_zoom_canvas_size()
        x = size / 2
        y = size / 2

        circle_r = 16
        cross_r = circle_r

        circle_color = "blue"
        crosshair_color = "orange"

        if not self.zoom_crosshair_ids:
            circle_id = self.zoom_canvas.create_oval(
                x - circle_r,
                y - circle_r,
                x + circle_r,
                y + circle_r,
                outline=circle_color,
                width=1,
                tags="zoom_crosshair",
            )
            hline_id = self.zoom_canvas.create_line(
                x - cross_r,
                y,
                x + cross_r,
                y,
                fill=crosshair_color,
                width=1,
                tags="zoom_crosshair",
            )
            vline_id = self.zoom_canvas.create_line(
                x,
                y - cross_r,
                x,
                y + cross_r,
                fill=crosshair_color,
                width=1,
                tags="zoom_crosshair",
            )
            self.zoom_crosshair_ids = [circle_id, hline_id, vline_id]
        else:
            circle_id, hline_id, vline_id = self.zoom_crosshair_ids
            self.zoom_canvas.coords(
                circle_id,
                x - circle_r,
                y - circle_r,
                x + circle_r,
                y + circle_r,
            )
            self.zoom_canvas.coords(hline_id, x - cross_r, y, x + cross_r, y)
            self.zoom_canvas.coords(vline_id, x, y - cross_r, x, y + cross_r)
            self.zoom_canvas.itemconfigure(circle_id, outline=circle_color)
            self.zoom_canvas.itemconfigure(hline_id, fill=crosshair_color)
            self.zoom_canvas.itemconfigure(vline_id, fill=crosshair_color)

        for item_id in self.zoom_crosshair_ids:
            self.zoom_canvas.tag_raise(item_id)

        self._update_zoom_extended_crosshair()

    def _hide_zoom_crosshair(self) -> None:
        if self.zoom_canvas is None:
            return

        for item_id in self.zoom_crosshair_ids:
            self.zoom_canvas.delete(item_id)
        self.zoom_crosshair_ids = []

    def _update_zoom_extended_crosshair(self) -> None:
        if self.zoom_canvas is None:
            return

        if not self.extended_crosshair_enabled.get():
            self._hide_zoom_extended_crosshair()
            return

        size = self._get_zoom_canvas_size()
        x = size / 2
        y = size / 2

        length = max(5, min(400, int(self.extended_crosshair_length.get())))

        # Keep it inside the zoom canvas
        max_len = max(1, int(size / 2) - 2)
        length = min(length, max_len)

        if not self.zoom_extended_crosshair_ids:
            hline_id = self.zoom_canvas.create_line(
                x - length,
                y,
                x + length,
                y,
                fill="lime",
                width=1,
                tags="zoom_extended_crosshair",
            )
            vline_id = self.zoom_canvas.create_line(
                x,
                y - length,
                x,
                y + length,
                fill="lime",
                width=1,
                tags="zoom_extended_crosshair",
            )
            self.zoom_extended_crosshair_ids = [hline_id, vline_id]
        else:
            hline_id, vline_id = self.zoom_extended_crosshair_ids
            self.zoom_canvas.coords(hline_id, x - length, y, x + length, y)
            self.zoom_canvas.coords(vline_id, x, y - length, x, y + length)

        for item_id in self.zoom_extended_crosshair_ids:
            self.zoom_canvas.tag_raise(item_id)

    def _hide_zoom_extended_crosshair(self) -> None:
        if self.zoom_canvas is None:
            return

        for item_id in self.zoom_extended_crosshair_ids:
            try:
                self.zoom_canvas.delete(item_id)
            except Exception as e:
                logger.warning(f"Failed to delete zoom extended crosshair item: {e}")
        self.zoom_extended_crosshair_ids = []

    def _change_femoral_axis_length(self, delta: int) -> None:
        new_len = max(2, min(300, int(self.femoral_axis_proj_length.get()) + delta))
        if new_len != self.femoral_axis_proj_length.get():
            self.femoral_axis_proj_length.set(new_len)
            self._update_femoral_axis_overlay()

    def _toggle_femoral_axis(self) -> None:
        enabled = self.femoral_axis_enabled.get()
        self.femoral_axis_count_scale.config(state="normal" if enabled else "disabled")
        self.femoral_axis_whisker_tip_length_scale.config(
            state="normal" if enabled else "disabled"
        )

        if enabled and self.hover_enabled.get():
            self.hover_enabled.set(False)
            self.radius_scale.config(state="disabled")
            self._hide_hover_circle()

        if not enabled:
            self._clear_femoral_axis_overlay()
        else:
            self._update_femoral_axis_overlay()

    def _on_femoral_axis_whisker_tip_length_change(self, _value: str) -> None:
        if not self.femoral_axis_enabled.get():
            return
        new_len = max(1, min(80, int(self.femoral_axis_whisker_tip_length.get())))
        self.femoral_axis_whisker_tip_length.set(new_len)
        self._update_femoral_axis_overlay()

    def _on_femoral_axis_count_change(self, _value: str) -> None:
        if not self.femoral_axis_enabled.get():
            return
        count = max(1, min(20, int(self.femoral_axis_count.get())))
        self.femoral_axis_count.set(count)
        self._update_femoral_axis_overlay()

    def _clear_femoral_axis_overlay(self) -> None:
        for item_id in self.femoral_axis_item_ids:
            try:
                self.canvas.delete(item_id)
            except Exception as e:
                logger.warning(f"Failed to delete femoral axis item: {e}")
        self.femoral_axis_item_ids = []

    def _change_femoral_axis_whisker_tip_length(self, delta: int) -> None:
        new_len = max(
            1,
            min(80, int(self.femoral_axis_whisker_tip_length.get()) + delta),
        )
        if new_len != self.femoral_axis_whisker_tip_length.get():
            self.femoral_axis_whisker_tip_length.set(new_len)
            self._update_femoral_axis_overlay()

    def _get_active_femoral_axis_line_screen(
        self,
    ) -> Optional[Tuple[float, float, float, float]]:
        if not self.current_image:
            return None
        if not self.femoral_axis_enabled.get():
            return None

        landmark = self.selected_landmark.get()
        if landmark not in ("L-FA", "R-FA"):
            return None

        points = self._get_line_points(landmark)
        if len(points) >= 2:
            x1, y1 = self._img_to_screen(*points[0])
            x2, y2 = self._img_to_screen(*points[1])
            return x1, y1, x2, y2

        if len(points) == 1 and self.last_mouse_canvas_pos is not None:
            mouse_x, mouse_y = self.last_mouse_canvas_pos
            x0, y0, x1, y1 = self._display_rect()
            if x0 <= mouse_x < x1 and y0 <= mouse_y < y1:
                sx, sy = self._img_to_screen(*points[0])
                return sx, sy, mouse_x, mouse_y

        return None

    def _update_femoral_axis_overlay(self) -> None:
        self._clear_femoral_axis_overlay()

        line = self._get_active_femoral_axis_line_screen()
        if line is None:
            return

        x1, y1, x2, y2 = line
        vx = x2 - x1
        vy = y2 - y1
        mag = float((vx * vx + vy * vy) ** 0.5)
        if mag < 1e-6:
            return

        tx = vx / mag
        ty = vy / mag
        nx = -ty
        ny = tx

        n_proj = max(1, int(self.femoral_axis_count.get()))
        proj_len = float(self.femoral_axis_proj_length.get())
        cap_half = float(self.femoral_axis_whisker_tip_length.get())

        for i in range(1, n_proj + 1):
            frac = i / (n_proj + 1.0)
            cx = x1 + frac * vx
            cy = y1 + frac * vy

            ax = cx - proj_len * nx
            ay = cy - proj_len * ny
            bx = cx + proj_len * nx
            by = cy + proj_len * ny

            main_id = self.canvas.create_line(
                ax,
                ay,
                bx,
                by,
                fill="magenta",
                width=2,
                tags="femoral_axis",
            )
            cap1_id = self.canvas.create_line(
                ax - cap_half * tx,
                ay - cap_half * ty,
                ax + cap_half * tx,
                ay + cap_half * ty,
                fill="magenta",
                width=2,
                tags="femoral_axis",
            )
            cap2_id = self.canvas.create_line(
                bx - cap_half * tx,
                by - cap_half * ty,
                bx + cap_half * tx,
                by + cap_half * ty,
                fill="magenta",
                width=2,
                tags="femoral_axis",
            )
            self.femoral_axis_item_ids.extend([main_id, cap1_id, cap2_id])

        for item_id in self.femoral_axis_item_ids:
            try:
                self.canvas.tag_raise(item_id)
            except Exception:
                pass
        self.canvas.tag_raise("marker")

    def _clear_zoom_landmark_overlay(self) -> None:
        if self.zoom_canvas is None:
            return

        for item_id in getattr(self, "zoom_landmark_overlay_ids", []):
            try:
                self.zoom_canvas.delete(item_id)
            except Exception as e:
                logger.warning(f"Failed to delete zoom landmark overlay item: {e}")
        self.zoom_landmark_overlay_ids = []

    def _is_line_landmark(self, lm: str) -> bool:
        return lm in self.line_landmarks

    def _get_line_points(self, lm: str) -> List[Tuple[float, float]]:
        pts, _quality = self._get_annotations()
        val = pts.get(lm)
        if val is None:
            return []

        out: List[Tuple[float, float]] = []

        if (
            isinstance(val, tuple)
            and len(val) == 2
            and all(isinstance(v, (int, float)) for v in val)
        ):
            return [(float(val[0]), float(val[1]))]

        if isinstance(val, list):
            for p in val:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    try:
                        out.append((float(p[0]), float(p[1])))
                    except (TypeError, ValueError):
                        pass

        return out[:2]

    def _set_line_points(self, lm: str, pts_list: List[Tuple[float, float]]) -> None:
        self.annotations.setdefault(str(self.current_image_path), {})[lm] = [
            (float(x), float(y)) for x, y in pts_list[:2]
        ]
        if lm in self.landmark_found:
            self.landmark_found[lm].set(len(pts_list) > 0)

    def _clamp_img_point(self, xi: float, yi: float) -> Tuple[float, float]:
        if not self.current_image:
            return xi, yi
        w, h = self.current_image.size
        xi = min(max(xi, 0.0), float(w - 1))
        yi = min(max(yi, 0.0), float(h - 1))
        return round(xi, 1), round(yi, 1)

    def _find_line_point_hit(
        self, lm: str, screen_x: float, screen_y: float
    ) -> Optional[int]:
        pts = self._get_line_points(lm)
        if not pts:
            return None

        best_idx = None
        best_dist2 = float("inf")
        tol2 = float(self.drag_tolerance_px * self.drag_tolerance_px)

        for i, (xi, yi) in enumerate(pts):
            xs, ys = self._img_to_screen(xi, yi)
            d2 = (xs - screen_x) ** 2 + (ys - screen_y) ** 2
            if d2 <= tol2 and d2 < best_dist2:
                best_dist2 = d2
                best_idx = i

        return best_idx

    def _point_to_segment_distance_px(
        self,
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

    def _is_line_hit(self, lm: str, screen_x: float, screen_y: float) -> bool:
        pts = self._get_line_points(lm)
        if len(pts) != 2:
            return False

        (x1i, y1i), (x2i, y2i) = pts
        x1s, y1s = self._img_to_screen(x1i, y1i)
        x2s, y2s = self._img_to_screen(x2i, y2i)

        dist = self._point_to_segment_distance_px(
            screen_x, screen_y, x1s, y1s, x2s, y2s
        )
        return dist <= float(self.drag_line_tolerance_px)

    def _clear_line_preview(self) -> None:
        if self.line_preview_id is not None:
            try:
                self.canvas.delete(self.line_preview_id)
            except Exception as e:
                logger.warning(f"Failed to delete line preview: {e}")
            self.line_preview_id = None

    def _update_line_preview(self, mouse_x: float, mouse_y: float) -> None:
        lm = self.selected_landmark.get()
        if not lm or not self._is_line_landmark(lm):
            self._clear_line_preview()
            return

        pts = self._get_line_points(lm)
        if len(pts) != 1:
            self._clear_line_preview()
            return

        x0, y0 = self._img_to_screen(*pts[0])

        if self.line_preview_id is None:
            self.line_preview_id = self.canvas.create_line(
                x0,
                y0,
                mouse_x,
                mouse_y,
                fill="cyan",
                width=2,
                dash=(4, 2),
                tags="line_preview",
            )
        else:
            self.canvas.coords(self.line_preview_id, x0, y0, mouse_x, mouse_y)

        try:
            self.canvas.tag_lower(self.line_preview_id, "marker")
        except Exception:
            pass

    def _refresh_zoom_landmark_overlay(self) -> None:
        self._clear_zoom_landmark_overlay()

        if self.zoom_canvas is None:
            return
        if not self.show_selected_landmark_in_zoom.get():
            return
        if self.current_image is None or self.current_image_path is None:
            return
        if self.zoom_src_rect is None:
            return

        lm = self.selected_landmark.get().strip()
        if not lm:
            return

        pts, _quality = self._get_annotations()
        size = self._get_zoom_canvas_size()
        if size <= 1:
            return

        src_left, src_top, src_right, src_bottom = self.zoom_src_rect
        src_w = src_right - src_left
        src_h = src_bottom - src_top
        if abs(src_w) < 1e-12 or abs(src_h) < 1e-12:
            return

        def img_to_zoom(px: float, py: float) -> Tuple[float, float]:
            zx = ((float(px) - src_left) / src_w) * size
            zy = ((float(py) - src_top) / src_h) * size
            return zx, zy

        overlay_ids: list[int] = []

        if self._is_line_landmark(lm):
            line_pts = self._get_line_points(lm)
            if not line_pts:
                return

            zoom_pts = [img_to_zoom(px, py) for px, py in line_pts]
            if len(zoom_pts) == 2:
                line_id = self.zoom_canvas.create_line(
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
                circle_id = self.zoom_canvas.create_oval(
                    zx - r,
                    zy - r,
                    zx + r,
                    zy + r,
                    outline="cyan",
                    width=2,
                    tags="zoom_landmark_overlay",
                )
                hline_id = self.zoom_canvas.create_line(
                    zx - r,
                    zy,
                    zx + r,
                    zy,
                    fill="cyan",
                    width=1,
                    tags="zoom_landmark_overlay",
                )
                vline_id = self.zoom_canvas.create_line(
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
            circle_id = self.zoom_canvas.create_oval(
                zx - r,
                zy - r,
                zx + r,
                zy + r,
                outline="cyan",
                width=2,
                tags="zoom_landmark_overlay",
            )
            hline_id = self.zoom_canvas.create_line(
                zx - r,
                zy,
                zx + r,
                zy,
                fill="cyan",
                width=1,
                tags="zoom_landmark_overlay",
            )
            vline_id = self.zoom_canvas.create_line(
                zx,
                zy - r,
                zx,
                zy + r,
                fill="cyan",
                width=1,
                tags="zoom_landmark_overlay",
            )
            overlay_ids.extend([circle_id, hline_id, vline_id])

        self.zoom_landmark_overlay_ids = overlay_ids

        for item_id in self.zoom_landmark_overlay_ids:
            try:
                self.zoom_canvas.tag_raise(item_id)
            except Exception:
                pass

        for item_id in getattr(self, "zoom_crosshair_ids", []):
            try:
                self.zoom_canvas.tag_raise(item_id)
            except Exception:
                pass

        for item_id in getattr(self, "zoom_extended_crosshair_ids", []):
            try:
                self.zoom_canvas.tag_raise(item_id)
            except Exception:
                pass

    # Builds the landmark selection table with visibility and status controls.

    def _build_landmark_panel(self) -> None:
        for w in self.lp_inner.winfo_children():
            w.destroy()
        self.landmark_visibility.clear()
        self.landmark_found.clear()
        self.landmark_flagged.clear()
        self.landmark_radio_widgets = {}
        self.landmark_found_widgets = {}
        self.landmark_flag_widgets = {}

        self.landmark_table = tk.Frame(self.lp_inner)
        self.landmark_table.pack(fill="x", padx=2, pady=2)
        self.landmark_table.grid_columnconfigure(0, minsize=55)
        self.landmark_table.grid_columnconfigure(1, minsize=140)
        self.landmark_table.grid_columnconfigure(2, minsize=80)
        self.landmark_table.grid_columnconfigure(3, minsize=60)

        key = (
            self._path_key(self.current_image_path)
            if self.json_path is not None and self.current_image_path is not None
            else str(self.current_image_path)
        )
        meta = self.landmark_meta.get(key, {})

        allowed = self._get_allowed_landmarks_for_current_view()
        visible_landmarks = [
            lm for lm in getattr(self, "landmarks", []) if lm in allowed
        ]

        for i, lm in enumerate(visible_landmarks, start=0):
            vis_var = tk.BooleanVar(value=True)
            found_var = tk.BooleanVar(value=False)
            flag_var = tk.BooleanVar(value=bool(meta.get(lm, {}).get("flag", False)))
            self.landmark_visibility[lm] = vis_var
            self.landmark_found[lm] = found_var
            self.landmark_flagged[lm] = flag_var
            tk.Checkbutton(
                self.landmark_table,
                variable=vis_var,
                command=self._draw_points,
                font=self.dialogue_font,
            ).grid(row=i, column=0, sticky="w", padx=(2, 4), pady=1)
            rb = tk.Radiobutton(
                self.landmark_table,
                text=lm,
                variable=self.selected_landmark,
                value=lm,
                anchor="w",
                justify="left",
                command=self._on_landmark_selected,
                font=self.dialogue_font,
            )
            rb.grid(row=i, column=1, sticky="w", padx=(2, 4), pady=1)
            self.landmark_radio_widgets[lm] = rb

            found_cb = tk.Checkbutton(
                self.landmark_table,
                text="",
                variable=found_var,
                font=self.dialogue_font,
                indicatoron=True,
                takefocus=0,
                command=lambda lm=lm: self._on_annotated_checkbox_toggled(lm),
            )
            found_cb.grid(row=i, column=2, sticky="w", padx=(2, 4), pady=1)
            self.landmark_found_widgets[lm] = found_cb

            flag_cb = tk.Checkbutton(
                self.landmark_table,
                text="",
                variable=flag_var,
                font=self.dialogue_font,
                indicatoron=True,
                takefocus=0,
                command=lambda lm=lm: self._on_flag_checkbox_toggled(lm),
            )
            flag_cb.grid(row=i, column=3, sticky="w", padx=(2, 4), pady=1)
            self.landmark_flag_widgets[lm] = flag_cb

        if visible_landmarks and not self.selected_landmark.get():
            self.selected_landmark.set(visible_landmarks[0])
        elif not visible_landmarks:
            self.selected_landmark.set("")

        self._load_note_for_selected_landmark()
        self._bind_landmark_scroll(True)

    # (4) Render base image (add to class)
    def _render_base_image(self) -> None:
        if not self.current_image:
            return

        self._recompute_transform()
        disp_w, disp_h = self.disp_size
        off_x, off_y = self.disp_off

        resized = self.current_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.img_obj = ImageTk.PhotoImage(resized)

        if self.base_img_item is None:
            self.base_img_item = self.canvas.create_image(
                off_x, off_y, anchor="nw", image=self.img_obj, tags="base"
            )
        else:
            self.canvas.itemconfigure(self.base_img_item, image=self.img_obj)
            self.canvas.coords(self.base_img_item, off_x, off_y)

    def _on_canvas_resize(self, _event=None) -> None:
        if not self.current_image:
            self._clear_line_preview()
            self._update_zoom_view(None, None)
            self._clear_femoral_axis_overlay()
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()
            return
        self._render_base_image()
        self._draw_points()
        for lm in ("LOB", "ROB"):
            self._update_overlay_for(lm)
        if self.last_mouse_canvas_pos is None:
            self._clear_line_preview()
            self._update_zoom_view(None, None)
            self._update_femoral_axis_overlay()
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()
            return

        mouse_x, mouse_y = self.last_mouse_canvas_pos
        x0, y0, x1, y1 = self._display_rect()
        if x0 <= mouse_x < x1 and y0 <= mouse_y < y1:
            self._update_zoom_view(mouse_x, mouse_y)
            self._update_line_preview(mouse_x, mouse_y)
            self._update_femoral_axis_overlay()
            if self.extended_crosshair_enabled.get():
                self._update_extended_crosshair(mouse_x, mouse_y)
            else:
                self._hide_extended_crosshair()
        else:
            self._clear_line_preview()
            self._update_zoom_view(None, None)
            self._clear_femoral_axis_overlay()
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()

    # Locks the initial window min-size after the first layout pass.
    def _lock_initial_minsize(self) -> None:
        self.update_idletasks()
        self._start_min_w = self.winfo_width()
        self._start_min_h = self.winfo_height()
        self.minsize(self._start_min_w, self._start_min_h)

    # Fits the window to required size and updates the minimum size.
    def _fit_window_and_set_min(self) -> None:
        self.minsize(0, 0)
        self.update_idletasks()
        req_w = self.winfo_reqwidth()
        req_h = self.winfo_reqheight()
        target_w = max(req_w, self._start_min_w)
        target_h = max(req_h, self._start_min_h)
        self.geometry(f"{target_w}x{target_h}")
        self.update_idletasks()
        self.minsize(target_w, target_h)

    # Enables or disables mousewheel scrolling for the landmark list.
    def _bind_landmark_scroll(self, bind: bool) -> None:
        if bind:
            self.lp_canvas.bind_all("<MouseWheel>", self._landmark_mousewheel)
        else:
            self.lp_canvas.unbind_all("<MouseWheel>")

    def _bind_image_list_scroll(self, bind: bool) -> None:
        if self.image_tree is None:
            return

        widgets: list[tk.Misc] = [self.image_tree]
        try:
            widgets.extend(self.image_tree.winfo_children())
        except Exception:
            pass

        if bind:
            for widget in widgets:
                try:
                    widget.bind("<MouseWheel>", self._image_list_mousewheel)
                    widget.bind("<Button-4>", self._image_list_mousewheel_linux_up)
                    widget.bind("<Button-5>", self._image_list_mousewheel_linux_down)
                except Exception:
                    pass
        else:
            for widget in widgets:
                try:
                    widget.unbind("<MouseWheel>")
                    widget.unbind("<Button-4>")
                    widget.unbind("<Button-5>")
                except Exception:
                    pass

    def _image_list_mousewheel(self, event) -> None:
        if self.image_tree is None:
            return
        if event.delta > 0:
            self.image_tree.yview_scroll(-1, "units")
        else:
            self.image_tree.yview_scroll(1, "units")

    def _image_list_mousewheel_linux_up(self, _event) -> None:
        if self.image_tree is not None:
            self.image_tree.yview_scroll(-1, "units")

    def _image_list_mousewheel_linux_down(self, _event) -> None:
        if self.image_tree is not None:
            self.image_tree.yview_scroll(1, "units")

    # Scrolls the landmark list in response to mouse wheel events.
    def _landmark_mousewheel(self, event) -> None:
        delta = -1 if event.delta > 0 else 1
        self.lp_canvas.yview_scroll(delta, "units")

    def _scroll_landmark_into_view(self, lm: str) -> None:
        rb = getattr(self, "landmark_radio_widgets", {}).get(lm)
        if rb is None:
            return
        self.lp_canvas.update_idletasks()
        bbox = self.lp_canvas.bbox("all")
        if not bbox:
            return
        y1, y2 = bbox[1], bbox[3]
        total = max(1, y2 - y1)
        canvas_h = self.lp_canvas.winfo_height()
        vis_top = self.lp_canvas.canvasy(0)
        vis_bottom = vis_top + canvas_h
        item_top = self._widget_y_in_inner(rb)
        item_bottom = item_top + rb.winfo_height()
        pad = 6
        if item_top < vis_top:
            new_top = max(y1, item_top - pad)
            self.lp_canvas.yview_moveto((new_top - y1) / total)
        elif item_bottom > vis_bottom:
            new_top = min(item_bottom + pad - canvas_h, y2 - canvas_h)
            new_top = max(y1, new_top)
            self.lp_canvas.yview_moveto((new_top - y1) / total)

    # Applies stored per-landmark settings when a landmark is selected.
    def _on_landmark_selected(self) -> None:
        lm = self.selected_landmark.get()
        self._apply_settings_to_ui_for(lm)
        self._sync_auto_tools_for_selected_landmark()
        self._load_note_for_selected_landmark()
        self._draw_points()
        self._refresh_zoom_landmark_overlay()
        if self.last_mouse_canvas_pos is not None:
            self._update_line_preview(*self.last_mouse_canvas_pos)
        else:
            self._clear_line_preview()
        self._update_femoral_axis_overlay()
        self.after_idle(self._scroll_landmark_into_view, lm)
        if self._landmark_ref_dialog is not None:
            self._landmark_ref_dialog.update_landmark(lm)

    def _get_landmark_meta(self, lm: str) -> Dict[str, Union[bool, str]]:
        if self.current_image_path is None:
            return {"flag": False, "note": ""}

        key = (
            self._path_key(self.current_image_path)
            if self.json_path is not None
            else str(self.current_image_path)
        )
        per_img = self.landmark_meta.setdefault(key, {})
        return per_img.setdefault(lm, {"flag": False, "note": ""})

    def _set_landmark_flag(self, lm: str, value: bool) -> None:
        meta = self._get_landmark_meta(lm)
        meta["flag"] = bool(value)

    def _get_landmark_flag(self, lm: str) -> bool:
        return bool(self._get_landmark_meta(lm).get("flag", False))

    def _set_landmark_note(self, lm: str, note: str) -> None:
        meta = self._get_landmark_meta(lm)
        meta["note"] = note

    def _get_landmark_note(self, lm: str) -> str:
        return str(self._get_landmark_meta(lm).get("note", ""))

    def _on_flag_checkbox_toggled(self, lm: str) -> None:
        if self.current_image_path is None:
            return

        flag_var = self.landmark_flagged.get(lm)
        is_flagged = flag_var.get() if flag_var is not None else False
        self._set_landmark_flag(lm, is_flagged)

        if not is_flagged:
            self._set_landmark_note(lm, "")

        if self.selected_landmark.get() == lm:
            self._load_note_for_selected_landmark()

        self.dirty = True
        self._maybe_autosave_current_image()

        pts, _quality = self._get_annotations()
        self._update_found_checks(pts)
        self._draw_points()

    def _on_annotated_checkbox_toggled(self, lm: str) -> None:
        if self.current_image_path is None:
            return

        pts, _quality = self._get_annotations()
        found_var = self.landmark_found.get(lm)
        is_checked = found_var.get() if found_var is not None else False

        if not is_checked:
            if lm not in pts:
                self.landmark_found[lm].set(False)
                self._update_found_checks(pts)
                return

            confirmed = messagebox.askyesno(
                "Delete Landmark",
                f'Are you sure you want to delete "{lm}"?\n\n'
                "All information for this landmark, including any flag and notes, will be deleted.",
            )

            if not confirmed:
                self.landmark_found[lm].set(True)
                self._update_found_checks(pts)
                return

            del pts[lm]
            key = (
                self._path_key(self.current_image_path)
                if self.json_path is not None
                else str(self.current_image_path)
            )
            if key in self.landmark_meta:
                self.landmark_meta[key].pop(lm, None)

            if self._is_line_landmark(lm):
                self._clear_line_preview()

            if lm in ("LOB", "ROB"):
                self.last_seed.pop(lm, None)
                if str(self.current_image_path) in self.seg_masks:
                    self.seg_masks[str(self.current_image_path)].pop(lm, None)
                self._remove_overlay_for(lm)

            self._clear_femoral_axis_overlay()
            self.dirty = True
            self._maybe_autosave_current_image()
            self._draw_points()
            self._refresh_zoom_landmark_overlay()
            self._load_note_for_selected_landmark()
            self._refresh_image_listbox()
            return

        if lm not in pts:
            self.landmark_found[lm].set(False)
            self._update_found_checks(pts)

    def _set_note_editor_enabled(self, enabled: bool) -> None:
        if self.note_text is None:
            return

        if enabled:
            self.note_text.configure(
                state="normal",
                bg="white",
                fg="black",
                insertbackground="black",
            )
        else:
            self.note_text.configure(
                state="disabled",
                bg="#E6E6E6",
                fg="#666666",
                insertbackground="#666666",
            )

    def _load_note_for_selected_landmark(self) -> None:
        if self.note_text is None:
            return

        lm = self.selected_landmark.get()
        can_edit = bool(lm) and self._get_landmark_flag(lm)
        note = self._get_landmark_note(lm) if can_edit else ""

        self.note_text_internal_update = True
        self.note_text.configure(state="normal")
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", note)
        self.note_text.edit_modified(False)
        self.note_text_internal_update = False

        self._set_note_editor_enabled(can_edit)

    def _save_note_for_selected_landmark(self) -> None:
        if self.note_text is None or self.current_image_path is None:
            return

        lm = self.selected_landmark.get()
        if not lm:
            return

        if not self._get_landmark_flag(lm):
            self._set_landmark_note(lm, "")
            return

        note = self.note_text.get("1.0", "end-1c")
        self._set_landmark_note(lm, note)

    def _on_note_text_modified(self, _event=None) -> None:
        if self.note_text is None:
            return
        if self.note_text_internal_update:
            self.note_text.edit_modified(False)
            return
        if not self.note_text.edit_modified():
            return

        self._save_note_for_selected_landmark()
        self.note_text.edit_modified(False)
        self.dirty = True
        self._maybe_autosave_current_image()

    def _bind_shortcut(self, sequence: str, callback) -> None:
        def wrapper(event):
            if self._note_text_shortcuts_blocked():
                return "break"
            return callback(event)

        self.bind(sequence, wrapper)

    def _note_text_shortcuts_blocked(self) -> bool:
        if self.note_text is None:
            return False

        try:
            if str(self.note_text.cget("state")) != "normal":
                return False
        except Exception:
            return False

        focused = self.focus_get() is self.note_text

        try:
            px, py = self.winfo_pointerxy()
            hovered_widget = self.winfo_containing(px, py)
        except Exception:
            hovered_widget = None

        hovered = hovered_widget is self.note_text or (
            hovered_widget is not None
            and str(hovered_widget).startswith(str(self.note_text))
        )

        return focused and hovered

    def _sync_auto_tools_for_selected_landmark(self) -> None:
        lm = self.selected_landmark.get().strip()

        hover_landmarks = {"L-FHC", "R-FHC", "L-AC", "R-AC"}
        femoral_axis_landmarks = {"L-FA", "R-FA"}

        want_hover = lm in hover_landmarks
        want_femoral_axis = lm in femoral_axis_landmarks

        if want_hover:
            if not self.hover_enabled.get():
                self.hover_enabled.set(True)
            if self.femoral_axis_enabled.get():
                self.femoral_axis_enabled.set(False)
            self._toggle_hover()
            self._toggle_femoral_axis()
            return

        if want_femoral_axis:
            if not self.femoral_axis_enabled.get():
                self.femoral_axis_enabled.set(True)
            if self.hover_enabled.get():
                self.hover_enabled.set(False)
            self._toggle_femoral_axis()
            self._toggle_hover()
            return

        changed = False

        if self.hover_enabled.get():
            self.hover_enabled.set(False)
            changed = True

        if self.femoral_axis_enabled.get():
            self.femoral_axis_enabled.set(False)
            changed = True

        if changed:
            self._toggle_hover()
            self._toggle_femoral_axis()
        else:
            self._hide_hover_circle()
            self._clear_femoral_axis_overlay()

    def _change_selected_landmark(self, step: int) -> None:
        if not getattr(self, "landmarks", None):
            return
        if not self.landmarks:
            return
        current = self.selected_landmark.get()
        if current in self.landmarks:
            idx = self.landmarks.index(current)
        else:
            idx = 0
        idx = idx + step
        if idx < 0 or idx >= len(self.landmarks):
            return
        new_lm = self.landmarks[idx]
        if new_lm != current:
            self.selected_landmark.set(new_lm)
            self._on_landmark_selected()

    def _on_arrow_up(self, event) -> str:
        self._change_selected_landmark(-1)
        return "break"

    def _on_arrow_down(self, event) -> str:
        self._change_selected_landmark(1)
        return "break"

    # Toggles visibility for all landmarks and redraws markers.
    def _set_all_visibility(self, value: bool) -> None:
        for var in self.landmark_visibility.values():
            var.set(value)
        self._draw_points()

    def load_landmarks_from_csv(self, path: Optional[Union[Path, str]] = None) -> None:
        if path is None:
            if not self._maybe_save_before_destructive_action("load point name CSV"):
                return
            self.abs_csv_path = filedialog.askopenfilename(
                initialdir=BASE_DIR, filetypes=[("CSV File", ("*.csv"))]
            )
        else:
            self.abs_csv_path = str(path)

        self.json_path = None
        self.json_dir = None
        self.json_data = {"landmarks": [], "views": {}, "images": []}
        self.allowed_views = {}
        self.images = []
        self.image_index_map = {}
        self.current_image_index = -1
        self.saved_image_snapshots.clear()
        self.current_view_var.set("")
        if self.view_dropdown is not None:
            self.view_dropdown["values"] = ()
        self.current_image_flag = False

        isolated_data_path = Path(BASE_DIR.parent / "data")
        db_name = extract_filename(Path(self.abs_csv_path).with_suffix(".db"))

        self.db_path = Path(isolated_data_path / db_name)
        self._init_database()
        df: pd.DataFrame = pd.read_csv(self.abs_csv_path)

        self.csv_path_column = self._detect_path_column(df)

        # Removing columns that we know are not landmarks, the rest are assumed to be landmarks
        df.drop(
            columns=["image_quality", self.csv_path_column],
            inplace=True,
            errors="ignore",
        )

        self.landmarks = list(df.columns)
        if self.landmarks:
            self.selected_landmark.set(self.landmarks[0])
        self._build_landmark_panel()
        self._import_csv_to_db()

    def _init_database(self) -> None:
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS annotations (
                    image_filename TEXT PRIMARY KEY,
                    image_path TEXT,
                    image_quality INTEGER DEFAULT 0,
                    data BLOB, -- JSON blob of all landmarks
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified INTEGER DEFAULT 0
                )
                """)
                conn.execute("""
                CREATE INDEX IF NOT EXISTS image_filename
                ON annotations(image_filename DESC)
                """)
                cols = [
                    elem[1]
                    for elem in conn.execute("""
                PRAGMA table_info(annotations)
                """)
                ]

                if "verified" not in cols:
                    conn.execute("""
                    ALTER TABLE annotations ADD COLUMN verified INTEGER DEFAULT 0
                    """)
                conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Failed to initialize database:\n{e}\n\nAnnotations will not be saved.",
            )
        return

    def _db_is_populated(self) -> bool:
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM annotations")
                count = cursor.fetchone()[0]
            return count > 0
        except sqlite3.Error:
            return False

    def _import_csv_to_db(self) -> None:
        try:
            df = pd.read_csv(self.abs_csv_path)
        except Exception as e:
            messagebox.showerror(
                "CSV Error",
                f"Failed to read CSV file:\n{e}",
            )
            return

        col = self._detect_path_column(df)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()

                for _, row in df.iterrows():
                    path = str(row[col])
                    try:
                        quality = int(row.get("image_quality", 0))
                    except (ValueError, TypeError):
                        quality = 0
                    landmark_data = {}

                    for lm in self.landmarks:
                        val = row.get(lm, "")
                        if pd.isna(val) or not str(val).strip():
                            continue  # Skip empty values entirely

                        # Parse the string representation back to list
                        try:
                            parsed = ast.literal_eval(str(val))
                            landmark_data[lm] = (
                                parsed  # Store as actual list, not string
                            )
                        except (ValueError, SyntaxError):
                            # If parsing fails, skip this landmark
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

    # Prompts to save pending changes before destructive operations.
    def _maybe_save_before_destructive_action(self, why: str = "continue") -> bool:
        if not self.current_image_path:
            return True

        has_unsaved_changes = (
            self._current_image_has_unsaved_changes()
            if self.json_path is not None
            and self._get_current_image_record() is not None
            else self.dirty
        )

        if not has_unsaved_changes:
            return True

        should_save = messagebox.askyesno(
            "Unsaved annotations",
            "You have unsaved annotation changes for this image.\n"
            f"Do you want to save before you {why}?",
        )
        if should_save:
            return self.save_annotations()

        return True

    # Handles window close, offering to save unsaved annotations.
    def _on_close(self) -> None:
        if not self._maybe_save_before_destructive_action("exit"):
            return
        self.window_close_flag = True
        if self._onedrive_backup_timer is not None:
            self.after_cancel(self._onedrive_backup_timer)
            self._onedrive_backup_timer = None
        if self.json_path is not None and not self._onedrive_upload_in_flight:
            # Non-daemon thread so Python waits for it during shutdown
            # instead of killing it mid-write (which crashes stdout).
            t = threading.Thread(
                target=self.onedrive_backup.upload_backup_sync,
                args=(self.json_path,),
                daemon=False,
            )
            t.start()
            # Give the upload a moment to finish before tearing down Tk.
            # If it takes longer, Python shutdown will still wait for the
            # non-daemon thread — but Tk will already be gone.
            t.join(timeout=2.0)
        if self.db_path is not None:
            self._export_db_to_csv()
        self.destroy()

    # Opens an image, prepares canvas, and loads saved points.
    def load_image(self) -> None:
        if not self._maybe_save_before_destructive_action("load another image"):
            return
        abs_path = filedialog.askopenfilename(
            initialdir=BASE_DIR,
            filetypes=[("Image files", ("*.png", "*.jpg", "*.jpeg", "*.bmp", ".tif"))],
        )
        if not abs_path:
            return

        self.absolute_current_image_path = Path(abs_path)
        self.load_image_from_path(Path(abs_path))
        if self.landmarks:
            self.selected_landmark.set(self.landmarks[0])

        return

    def _get_image_index_from_directory(self) -> Tuple[int, list]:
        if self.absolute_current_image_path is None:
            return 0, []
        # Grab the directory that the current image lives in
        current_image_directory = (
            Path(self.absolute_current_image_path).resolve().parent
        )
        current_image_name = extract_filename(self.absolute_current_image_path)

        all_files = [
            file.name
            for file in current_image_directory.iterdir()
            if file.suffix.lower() in self.possible_image_suffix
        ]

        all_files.sort()

        try:
            idx = all_files.index(current_image_name)
        except ValueError:
            # If current image not found, check case-insensitive match
            current_lower = current_image_name.lower()
            for i, fname in enumerate(all_files):
                if fname.lower() == current_lower:
                    idx = i
                    break
            else:
                raise ValueError(
                    f"Current image '{current_image_name}' not found in directory. "
                    f"Available files: {all_files[:5]}..."  # Show first 5 for debugging
                )

        return idx, all_files

    def _next_image(self) -> None:
        if self.json_path is not None and self.images:
            if self.current_image_index >= len(self.images) - 1:
                messagebox.showwarning(
                    "End of List", "You have reached the last image in the JSON."
                )
                return

            if not self._maybe_save_before_destructive_action("switch images"):
                return

            self._navigation_in_progress = True
            self._suspend_image_tree_select = True
            try:
                self.current_image_index += 1
                self.load_image_from_path(self.images[self.current_image_index])
            finally:
                self._navigation_in_progress = False
                self._suspend_image_tree_select = False
            return

        # Loads the next image in the current directory
        # self._maybe_save_before_destructive_action("load next image")
        self.save_annotations()
        if self.queue_mode:
            # Queue mode: move backward through unannotated list
            if self.queue_index >= len(self.unannotated_queue) - 1:
                messagebox.showwarning(
                    "Start of Queue",
                    "You're at the beginning of the unannotated images.",
                )
                return

            self.queue_index += 1
            prev_path = self.unannotated_queue[self.queue_index]
            self.absolute_current_image_path = prev_path
            self.load_image_from_path(prev_path)
            self._update_queue_status()

        elif self.check_csv_mode:
            if self.csv_index >= len(self.csv_path_queue) - 1:
                return
            self.csv_index += 1
            prev_path = self.csv_path_queue[self.csv_index]
            self.absolute_current_image_path = prev_path
            self.load_image_from_path(Path(prev_path))
            self._update_queue_status()

        else:
            idx, all_files = self._get_image_index_from_directory()
            current_path = self.absolute_current_image_path
            if current_path is None or not all_files:
                return
            if len(all_files) == idx + 1:
                messagebox.showwarning(
                    "End of Directory",
                    "You've reached the end of the current image directory, please use"
                    "'Load Image' to find a new image, or use 'Prev Image' to move backward",
                )
            else:
                self.absolute_current_image_path = Path(
                    current_path.resolve().parent / all_files[idx + 1]
                )
                self.load_image_from_path(Path(self.absolute_current_image_path))

    def _prev_image(self) -> None:
        if self.json_path is not None and self.images:
            if self.current_image_index <= 0:
                messagebox.showwarning(
                    "Beginning of List", "You are at the first image in the JSON."
                )
                return

            if not self._maybe_save_before_destructive_action("switch images"):
                return

            self._navigation_in_progress = True
            self._suspend_image_tree_select = True
            try:
                self.current_image_index -= 1
                self.load_image_from_path(self.images[self.current_image_index])
            finally:
                self._navigation_in_progress = False
                self._suspend_image_tree_select = False
            return

        # Loads the next image in the current directory
        # self._maybe_save_before_destructive_action("load next image")
        self.save_annotations()

        if self.queue_mode:
            # Queue mode: move backward through unannotated list
            if self.queue_index <= 0:
                messagebox.showwarning(
                    "Start of Queue",
                    "You're at the beginning of the unannotated images.",
                )
                return

            self.queue_index -= 1
            prev_path = self.unannotated_queue[self.queue_index]
            self.absolute_current_image_path = prev_path
            self.load_image_from_path(prev_path)
            self._update_queue_status()

        elif self.check_csv_mode:
            if self.csv_index <= 0:
                return
            self.csv_index -= 1
            prev_path = self.csv_path_queue[self.csv_index]
            self.absolute_current_image_path = prev_path
            self.load_image_from_path(Path(prev_path))
            self._update_queue_status()
        else:
            idx, all_files = self._get_image_index_from_directory()
            current_path = self.absolute_current_image_path
            if current_path is None or not all_files:
                return
            if idx == 0:
                messagebox.showwarning(
                    "Beginning of Directory",
                    "You've reached the beginning of the current image directory, please use 'Load Image' to find a new image, or use 'Next Image' to move forward",
                )
            else:
                self.absolute_current_image_path = Path(
                    current_path.resolve().parent / all_files[idx - 1]
                )
                self.load_image_from_path(Path(self.absolute_current_image_path))

    def _on_pg_down(self, event) -> None:
        self._next_image()
        return

    def _on_pg_up(self, event) -> None:
        self._prev_image()
        return

    def _on_backspace(self, event) -> None:
        self._delete_current_landmark()
        return

    def _on_1_press(self, event) -> None:
        self.change_image_quality(1)
        return

    def _on_2_press(self, event) -> None:
        self.change_image_quality(2)
        return

    def _on_3_press(self, event) -> None:
        self.change_image_quality(3)
        return

    def _on_4_press(self, event) -> None:
        self.change_image_quality(4)
        return

    def change_image_quality(self, val: int) -> None:
        self.current_image_quality = val
        if self.current_image_path:
            self.path_var.set(extract_filename(self.current_image_path))
            self.quality_var.set(str(self.current_image_quality))
        self.dirty = True
        # Auto-save to database immediately after quality change
        self._auto_save_to_db()
        return

    def _update_path_var(self) -> None:
        if self.current_image_path:
            self.path_var.set(extract_filename(self.current_image_path))
            self.quality_var.set(str(self.current_image_quality))
        self.dirty = True

    def load_image_from_path(self, path: Path) -> None:
        try:
            self.current_image = Image.open(path)

            if self.current_image.mode == "I;16":
                arr = np.array(self.current_image, dtype=np.uint16)

                lo = np.percentile(arr, 1)
                hi = np.percentile(arr, 99)

                arr = np.clip(arr, lo, hi)
                arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)

                img = Image.fromarray(arr, mode="L").convert("RGB")
                self.current_image = img
            self.current_image = self.current_image.convert("RGB")

        except Exception as e:
            messagebox.showerror("Load Image", f"Failed to open image:\n{e}")
            return

        json_record_loaded = self.json_path is not None and self.images
        if self.view_dropdown is not None:
            self.view_dropdown["values"] = list(self.allowed_views.keys())

        if json_record_loaded:
            resolved_path = path.resolve()
            self.current_image_path = resolved_path
            self.absolute_current_image_path = resolved_path
            self.current_image_index = (
                self.images.index(resolved_path) if resolved_path in self.images else -1
            )
            key = self._path_key(resolved_path)
            record = self._get_current_image_record()
            if record is not None:
                self.current_image_flag = bool(record.get("image_flag", False))
                self.image_flag_var.set(self.current_image_flag)
                self.current_image_direction = (
                    record.get("image_direction", "AP") or "AP"
                )
                self.image_direction_var.set(self.current_image_direction)
                self.annotations[key] = self._parse_annotations_for_record(record)
            else:
                self.current_image_flag = False
                self.image_flag_var.set(False)
                self.current_image_direction = "AP"
                self.image_direction_var.set("AP")
                self.annotations[key] = {}
                self.landmark_meta[key] = {}
            self.current_image_quality = 0
            self.current_view_var.set(self._get_current_view())
        else:
            rel_path = PurePath(path.resolve()).relative_to(
                BASE_DIR.resolve(), walk_up=True
            )
            self.current_image_path = Path(rel_path)
            self.absolute_current_image_path = path.resolve()
            self.current_image_flag = False
            self.image_flag_var.set(False)
            self.current_image_direction = "AP"
            self.image_direction_var.set("AP")
            self.current_view_var.set("")

        self._refresh_image_flag_checkbox_style()

        w, h = self.current_image.size
        self.canvas.config(width=w, height=h)
        self.canvas.delete("all")
        self.base_img_item = None
        self._remove_all_overlays()
        self.last_seed.clear()
        self._clear_line_preview()
        self._clear_femoral_axis_overlay()
        self.dragging_landmark = None
        self.dragging_point_index = None
        self.dragging_line_whole = False
        self.dragging_line_last_img_pos = None

        current_key = (
            self._path_key(self.current_image_path)
            if json_record_loaded and self.current_image_path is not None
            else str(self.current_image_path)
        )
        self.lm_settings.setdefault(current_key, {})
        self.annotations.setdefault(current_key, {})

        if not json_record_loaded:
            self.load_points(show_message=False)

        self._render_base_image()
        self.mouse_crosshair_ids = []
        self.extended_crosshair_ids = []
        self.zoom_extended_crosshair_ids = []
        self._hide_hover_circle()
        self.last_mouse_canvas_pos = None
        self._update_zoom_view(None, None)
        self._hide_zoom_extended_crosshair()
        self.dirty = False
        self._update_path_var()
        self.dirty = False

        if json_record_loaded:
            self._prompt_for_view_if_needed()
        else:
            self._rebuild_landmark_panel_for_view()

        self._load_note_for_selected_landmark()

        pts, _quality = self._get_annotations()
        self._update_found_checks(pts)
        self._draw_points()

        if json_record_loaded:
            self._refresh_saved_snapshot_for_current_image()

        self._refresh_image_listbox()

    def _prepare_landmark_data(self, for_json: Optional[bool] = None) -> dict:
        """Prepare landmark data for JSON or legacy database storage."""
        pts, _quality = self._get_annotations()
        key = (
            self._path_key(self.current_image_path)
            if self.json_path is not None and self.current_image_path is not None
            else str(self.current_image_path)
        )
        per_img_settings = self.lm_settings.get(key, {})
        per_img_meta = self.landmark_meta.get(key, {})
        use_json_format = self.json_path is not None if for_json is None else for_json

        landmark_data = {}
        all_landmarks = set(pts.keys()) | set(per_img_meta.keys())

        for lm in self.landmarks:
            if use_json_format and lm not in all_landmarks:
                continue
            if not use_json_format and lm not in pts:
                continue

            meta = per_img_meta.get(lm, {})
            is_flagged = bool(meta.get("flag", False))
            note = str(meta.get("note", ""))

            value = None
            if lm in pts:
                if self._is_line_landmark(lm):
                    line_pts = self._get_line_points(lm)
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
                        st = per_img_settings.get(lm, self._current_settings_dict())
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

    def _canonical_image_state_for_path(self, image_path: Path) -> str:
        key = self._path_key(image_path)
        idx = self.image_index_map.get(key)
        if idx is None:
            return ""

        record = self.json_data["images"][idx]
        state = {
            "image_path": record.get("image_path"),
            "image_flag": bool(record.get("image_flag", False)),
            "view": record.get("view"),
            "annotations": record.get("annotations", {}) or {},
        }
        return json.dumps(state, sort_keys=True, separators=(",", ":"))

    def _current_image_state_string(self) -> str:
        if self.current_image_path is None:
            return ""

        record = self._get_current_image_record()
        state = {
            "image_path": record.get("image_path")
            if record
            else str(self.current_image_path),
            "image_flag": bool(self.current_image_flag),
            "view": self.current_view_var.get().strip() or None,
            "annotations": self._prepare_landmark_data(for_json=True),
        }
        return json.dumps(state, sort_keys=True, separators=(",", ":"))

    def _refresh_saved_snapshot_for_current_image(self) -> None:
        if self.current_image_path is None:
            return
        self.saved_image_snapshots[self._path_key(self.current_image_path)] = (
            self._canonical_image_state_for_path(self.current_image_path)
        )

    def _current_image_has_unsaved_changes(self) -> bool:
        if self.current_image_path is None:
            return False

        key = self._path_key(self.current_image_path)
        current_state = self._current_image_state_string()
        saved_state = self.saved_image_snapshots.get(key)
        if saved_state is None:
            saved_state = self._canonical_image_state_for_path(self.current_image_path)
            self.saved_image_snapshots[key] = saved_state
        return current_state != saved_state

    def _maybe_autosave_current_image(self) -> bool:
        self.dirty = True
        self._refresh_image_listbox()

        autosave_var = getattr(self, "autosave_var", None)
        if autosave_var is not None and bool(autosave_var.get()):
            ok = self._save_json_file(show_success=False)
            if ok:
                self.dirty = False
            return ok

        return True

    def _auto_save_to_db(self) -> bool:
        """
        Auto-save annotations to database immediately after changes.
        Returns True on success, False on failure.
        Silent operation - no user feedback unless error occurs.
        """
        if not self.current_image_path or self.db_path is None:
            return False

        try:
            pts, quality = self._get_annotations()
            landmark_data = self._prepare_landmark_data()

            with sqlite3.connect(str(self.db_path)) as conn:
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
                        extract_filename(self.current_image_path),
                        str(self.current_image_path),
                        quality,
                        json.dumps(landmark_data),
                    ),
                )
                conn.commit()

            self.dirty = False
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

    # Writes annotations (and LOB/ROB settings) back to the CSV.
    def save_annotations(self) -> bool:
        """Save annotations. JSON is the primary format; SQLite/CSV kept for backup."""
        if not self.current_image_path:
            messagebox.showwarning("Save", "No image loaded.")
            return False

        return self._save_json_file(show_success=(PLATFORM == "Windows"))

        # Get annotation data
        _pts, quality = self._get_annotations()
        landmark_data = self._prepare_landmark_data()

        # Save to database with error handling
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
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
                        extract_filename(self.current_image_path),
                        str(self.current_image_path),
                        quality,
                        json.dumps(landmark_data),
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Failed to save annotations to database:\n{e}",
            )
            return False
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Unexpected error while saving:\n{e}",
            )
            return False

        # Export to CSV (periodic, not every save)
        self._export_db_to_csv()

        self.dirty = False
        if PLATFORM == "Windows":
            messagebox.showinfo("Saved", "Annotations saved")
        return True

    def _init_onedrive_credentials(self) -> None:
        """
        Initialize OneDrive credentials at app startup.

        If credentials don't exist, this will trigger the auth dialog.
        Runs in background thread to not block GUI startup.
        """

        def _init():
            try:
                self.onedrive_backup._ensure_initialized()
                logger.info("OneDrive credentials initialized")
            except Exception as e:
                logger.warning(f"OneDrive initialization failed: {e}")

        thread = threading.Thread(target=_init, daemon=True)
        thread.start()

    def _schedule_onedrive_backup(self, delay_ms: int = 5000) -> None:
        if self._onedrive_backup_timer is not None:
            self.after_cancel(self._onedrive_backup_timer)
        self._onedrive_backup_timer = self.after(delay_ms, self._fire_onedrive_backup)

    def _fire_onedrive_backup(self) -> None:
        self._onedrive_backup_timer = None
        if self.json_path is None or self._onedrive_upload_in_flight:
            return
        self._onedrive_upload_in_flight = True
        self._backup_to_onedrive(self.json_path)

    def _backup_to_onedrive(self, *paths: Path) -> None:
        files_to_backup = [p for p in paths if p is not None and p.exists()]
        if not files_to_backup:
            return

        def _on_done(success, total):
            self._onedrive_upload_in_flight = False
            logger.info(f"OneDrive backup: {success}/{total} files uploaded")

        self.onedrive_backup.backup_multiple(
            files_to_backup,
            callback=_on_done,
        )

    def _backup_with_progress_dialog(self, files: list) -> None:
        """
        Show a progress dialog while backing up files on close.
        Runs upload in background thread, updates GUI via polling.
        """
        # Create progress dialog
        dialog = tk.Toplevel(self)
        dialog.title("Backing up to OneDrive...")
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 150) // 2
        dialog.geometry(f"400x150+{x}+{y}")

        # Prevent closing via X button
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        status_var = tk.StringVar(value="Uploading to OneDrive...")
        status_label = ttk.Label(frame, textvariable=status_var, font=("Helvetica", 12))
        status_label.pack(pady=(0, 15))

        # Progress bar (indeterminate mode)
        progress = ttk.Progressbar(frame, mode="indeterminate", length=300)
        progress.pack(pady=10)
        progress.start(10)

        file_var = tk.StringVar(value="")
        file_label = ttk.Label(
            frame, textvariable=file_var, font=("Helvetica", 9), foreground="gray"
        )
        file_label.pack(pady=(10, 0))

        # Shared state for thread communication
        upload_state = {"done": False, "success": 0, "total": len(files), "current": ""}

        def do_upload():
            """Run uploads in background thread."""
            for fpath in files:
                if fpath.exists():
                    upload_state["current"] = fpath.name
                    try:
                        if self.onedrive_backup.upload_backup_sync(fpath):
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
                # Check again in 100ms
                dialog.after(100, check_progress)

        # Start upload thread
        upload_thread = threading.Thread(target=do_upload, daemon=True)
        upload_thread.start()

        # Start polling
        check_progress()

        # Wait for dialog to close (blocking but GUI-responsive)
        self.wait_window(dialog)

    def _export_db_to_csv(self) -> None:
        """Export database to CSV file with atomic write (temp file + rename)."""
        current_time = datetime.now()
        # save every so often, or save when the window is being closed
        if ((current_time - self.last_update).total_seconds() > 20) or (
            self.window_close_flag
        ):
            self.last_update = datetime.now()

            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT image_path, image_quality, data FROM annotations"
                    )
                    rows = cursor.fetchall()
            except sqlite3.Error as e:
                messagebox.showerror(
                    "Database Error",
                    f"Failed to read annotations from database:\n{e}",
                )
                return

            # Build DataFrame
            records = []
            for path, quality, data_json in rows:
                if path == None:
                    continue
                if quality == None:
                    continue
                if data_json == None:
                    continue

                record = {
                    self.csv_path_column: Path(path).resolve(),
                    "image_quality": quality,
                }

                try:
                    landmark_data = json.loads(data_json) if data_json else {}
                except json.JSONDecodeError:
                    landmark_data = {}

                for lm in self.landmarks:
                    if lm in landmark_data and landmark_data[lm]:
                        record[lm] = repr(landmark_data[lm])
                    else:
                        record[lm] = ""

                records.append(record)

            df = pd.DataFrame(records)

            # Ensure column order
            cols = [self.csv_path_column, "image_quality"] + self.landmarks
            df = df[[c for c in cols if c in df.columns]]

            # Determine final CSV path
            if self.abs_csv_path is None:
                return
            csv_path = Path(self.abs_csv_path)
            if self.check_csv_mode:
                dir = csv_path.parent
                csv_name = Path(extract_filename(csv_path))
                new_name = csv_name.stem + "_CHECKED.csv"
                csv_path = Path(dir / new_name)

            # Atomic write: write to temp file, then rename
            # This prevents corruption if the app crashes mid-write
            temp_path = csv_path.with_suffix(".csv.tmp")
            try:
                df.to_csv(str(temp_path), index=False)
                # Atomic rename (on same filesystem)
                temp_path.replace(csv_path)

                # Backup to OneDrive after successful local save
                self._backup_to_onedrive(csv_path)

            except OSError as e:
                messagebox.showerror(
                    "CSV Export Error",
                    f"Failed to save CSV file:\n{e}\n\nYour data is safe in the database.",
                )
                # Clean up temp file if it exists
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

    def _get_annotations(self) -> Tuple[Dict[str, AnnotationValue], int]:
        """Returns (points_dict, quality) for current image."""
        if self.current_image_path is not None:
            current_filename = PurePath(self.current_image_path).name
            keys_to_try = [str(self.current_image_path)]
            if self.json_path is not None:
                keys_to_try.insert(0, self._path_key(self.current_image_path))

            for key in keys_to_try:
                if key in self.annotations:
                    quality = self.current_image_quality
                    return self.annotations[key], quality

            # Fallback: match by filename
            for key in self.annotations.keys():
                if current_filename in key:
                    quality = self.current_image_quality
                    return self.annotations[key], quality

        return {}, 0

    def load_points(self, show_message: bool = True) -> None:
        if not self.current_image_path:
            if show_message:
                messagebox.showwarning("Load Points", "No image loaded.")
            return
        if self.abs_csv_path is None:
            if show_message:
                messagebox.showerror("Load Points", "CSV path is not configured.")
            return
        if not Path(self.abs_csv_path).exists():
            if show_message:
                messagebox.showerror(
                    "Load Points", f"CSV not found: {self.abs_csv_path}"
                )
            return
        try:
            df = pd.read_csv(self.abs_csv_path)
        except Exception as e:
            if show_message:
                messagebox.showerror("Load Points", f"Failed to read CSV:\n{e}")
            return
        if df.empty:
            self.annotations[str(self.current_image_path)] = {}
            self._update_found_checks({})
            if show_message:
                messagebox.showinfo("Load Points", "No saved points for this image.")
            return
        # We know that this is image_path
        # df_img_path_col = "image_path"  # this is just grabbing image_path
        df_img_path_col = self._detect_path_column(df)

        # rowdf = df.loc[df[col0] == self.current_image_path]
        rowdf = df.loc[df[df_img_path_col] == str(self.current_image_path)]
        if rowdf.empty:
            # Check if the current image filename is in any of the rows
            # Only if that fails do we reset the points values
            current_filename = PurePath(self.current_image_path).name
            found_filename = False
            for name in list(df[df_img_path_col]):
                if current_filename in name:
                    rowdf = df.loc[df[df_img_path_col] == name]
                    found_filename = True
                    break

            if found_filename is False:
                self.annotations[str(self.current_image_path)] = {}
                self._update_found_checks({})
                if show_message:
                    messagebox.showinfo(
                        "Load Points", "No saved points for this image."
                    )
                return
        row: pd.DataFrame = rowdf.iloc[0]
        pts = {}
        per_img_settings = self.lm_settings.setdefault(str(self.current_image_path), {})
        for lm in self.landmarks:
            val = row.get(lm, "")
            if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
                try:
                    arr = ast.literal_eval(val)
                except Exception:
                    continue
                if self._is_line_landmark(lm):
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
        self.annotations[str(self.current_image_path)] = pts
        try:
            self.current_image_quality = int(row.get("image_quality", 0))
        except (ValueError, TypeError):
            self.current_image_quality = 0
        self._update_found_checks(pts)
        self._draw_points()
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
                    self.last_seed[lm] = (int(sx), int(sy))
                except Exception:
                    self.last_seed.pop(lm, None)
                vis_var = self.landmark_visibility.get(lm)
                if (
                    self.last_seed.get(lm) is not None
                    and vis_var is not None
                    and vis_var.get()
                    and cv2 is not None
                ):
                    self._resegment_for(lm, apply_saved_settings=True)
                else:
                    self._update_overlay_for(lm)
        if show_message:
            messagebox.showinfo("Load Points", "Points loaded from CSV.")
        self._update_path_var()

    # Updates the disabled “Annotated” checkboxes based on available points.
    def _update_found_checks(self, pts_dict):
        key = (
            self._path_key(self.current_image_path)
            if self.json_path is not None and self.current_image_path is not None
            else str(self.current_image_path)
        )
        meta = self.landmark_meta.get(key, {})

        for lm in self.landmarks:
            var = self.landmark_found.get(lm)
            widget = getattr(self, "landmark_found_widgets", {}).get(lm)
            if var is not None:
                is_found = lm in pts_dict
                var.set(is_found)

                if widget is not None:
                    try:
                        widget.configure(
                            fg="green" if is_found else "black",
                            activeforeground="green" if is_found else "black",
                            selectcolor="#90EE90" if is_found else widget.cget("bg"),
                        )
                    except Exception:
                        pass

            fvar = self.landmark_flagged.get(lm)
            fwidget = getattr(self, "landmark_flag_widgets", {}).get(lm)
            is_flagged = bool(meta.get(lm, {}).get("flag", False))
            if fvar is not None:
                fvar.set(is_flagged)
            if fwidget is not None:
                try:
                    fwidget.configure(
                        fg="red" if is_flagged else "black",
                        activeforeground="red" if is_flagged else "black",
                        selectcolor="#FFB6B6" if is_flagged else fwidget.cget("bg"),
                    )
                except Exception:
                    pass

    # Draws landmark markers/labels and syncs overlays and pair lines.
    def _draw_points(self) -> None:
        self.canvas.delete("marker")
        if not self.current_image_path:
            self._clear_line_preview()
            self._clear_femoral_axis_overlay()
            return
        # pts = self.annotations.get(self.current_image_path, {})
        pts, quality = self._get_annotations()
        self._update_found_checks(pts)
        current_image_verified = self._is_current_image_verified()
        x_curr, y_curr = self._img_to_screen(0, 0)
        label_font = self.landmark_font.copy()
        label_font.configure(size=30)

        selected_lm = self.selected_landmark.get()
        if self._is_line_landmark(selected_lm):
            landmark_is_labeled = len(self._get_line_points(selected_lm)) > 0
        else:
            landmark_is_labeled = selected_lm in pts.keys()

        if selected_lm:
            self.canvas.create_text(
                x_curr,
                y_curr,
                text=selected_lm,
                fill=("#FFCC66" if landmark_is_labeled else "#FF8066"),
                font=label_font,
                tags="marker",
                anchor="nw",
            )

        key = (
            self._path_key(self.current_image_path)
            if self.json_path is not None
            else str(self.current_image_path)
        )
        meta = self.landmark_meta.get(key, {})

        for lm, val in pts.items():
            vis_var = self.landmark_visibility.get(lm)
            if vis_var is not None and not vis_var.get():
                continue

            drawing_current_selected = lm == self.selected_landmark.get()
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
            font = (
                self.landmark_font if drawing_current_selected else self.dialogue_font
            )
            shadow_font = font.copy()
            shadow_font.configure(size=font.cget("size") + 1)

            if self._is_line_landmark(lm):
                line_pts = self._get_line_points(lm)
                if not line_pts:
                    continue

                screen_pts = [self._img_to_screen(x, y) for x, y in line_pts]

                line_color = "blue" if drawing_current_selected else "red"
                if len(screen_pts) == 2:
                    xs1, ys1 = screen_pts[0]
                    xs2, ys2 = screen_pts[1]
                    self.canvas.create_line(
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
                    self.canvas.create_oval(
                        xs - r,
                        ys - r,
                        xs + r,
                        ys + r,
                        outline=line_color,
                        width=2,
                        tags="marker",
                    )

                self.canvas.create_text(
                    label_x - 1,
                    label_y - 1,
                    text=lm,
                    fill="black",
                    font=shadow_font,
                    tags="marker",
                )
                self.canvas.create_text(
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
            xs, ys = self._img_to_screen(x, y)

            r = 5
            self.canvas.create_oval(
                xs - r,
                ys - r,
                xs + r,
                ys + r,
                outline=oval_color,
                width=2,
                tags="marker",
            )
            if self.check_csv_mode and drawing_current_selected:
                self.canvas.create_oval(
                    xs - 10 * r,
                    ys - 10 * r,
                    xs + 10 * r,
                    ys + 10 * r,
                    outline=oval_color,
                    width=6,
                    tags="marker",
                )

            self.canvas.create_text(
                xs - 1,
                ys - y_offset_label - 1,
                text=lm,
                fill="black",
                font=shadow_font,
                tags="marker",
            )
            self.canvas.create_text(
                xs,
                ys - y_offset_label,
                text=lm,
                fill=text_color,
                font=font,
                tags="marker",
            )
        for lm in ("LOB", "ROB"):
            self._update_overlay_for(lm)
        self._update_pair_lines()
        self._update_femoral_axis_overlay()

    # Removes any connector lines between paired landmarks.
    def _remove_pair_lines(self):
        for key, line_id in list(self.pair_line_ids.items()):
            try:
                self.canvas.delete(line_id)
            except Exception as e:
                logger.warning(f"Failed to delete pair line {key}: {e}")
            self.pair_line_ids.pop(key, None)

    # Finds a landmark by lowercase name, returning the exact key.
    def _find_landmark_key(self, name_lower: str):
        for k in self.landmarks:
            if k.lower() == name_lower:
                return k
        return None

    # Adds or updates connector lines between DF/PF pairs if visible.
    def _update_pair_lines(self) -> None:
        if not self.current_image_path:
            self._remove_pair_lines()
            return
        # pts = self.annotations.get(self.current_image_path, {})
        pts, quality = self._get_annotations()
        pairs = [("ldf", "lpf"), ("rdf", "rpf")]
        color = "#00FFFF"
        for a, b in pairs:
            key = f"{a}_{b}"
            ka = self._find_landmark_key(a)
            kb = self._find_landmark_key(b)
            if ka is None or kb is None:
                return
            if ka in pts and kb in pts:
                va = self.landmark_visibility.get(ka)
                vb = self.landmark_visibility.get(kb)
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
                    xs1, ys1 = self._img_to_screen(x1, y1)
                    xs2, ys2 = self._img_to_screen(x2, y2)
                    if key in self.pair_line_ids:
                        self.canvas.coords(self.pair_line_ids[key], xs1, ys1, xs2, ys2)
                    else:
                        self.pair_line_ids[key] = self.canvas.create_line(
                            xs1, ys1, xs2, ys2, fill=color, width=2, tags="pairline"
                        )
                    try:
                        self.canvas.tag_lower(self.pair_line_ids[key], "marker")
                    except Exception as e:
                        logger.warning(f"Failed to lower pair line {key}: {e}")
                    continue
            if key in self.pair_line_ids:
                try:
                    self.canvas.delete(self.pair_line_ids[key])
                except Exception as e:
                    logger.warning(f"Failed to delete pair line {key}: {e}")
                self.pair_line_ids.pop(key, None)

    def _toggle_extended_crosshair(self) -> None:
        enabled = self.extended_crosshair_enabled.get()
        self.crosshair_length_scale.config(state="normal" if enabled else "disabled")

        if not enabled:
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()
        else:
            if self.last_mouse_canvas_pos is not None:
                x, y = self.last_mouse_canvas_pos
                self._update_extended_crosshair(x, y)
            self._update_zoom_extended_crosshair()

    def _on_extended_crosshair_length_change(self, _value: str) -> None:
        if not self.extended_crosshair_enabled.get():
            return

        length = max(5, min(400, self.extended_crosshair_length.get()))
        self.extended_crosshair_length.set(length)

        if self.last_mouse_canvas_pos is not None:
            x, y = self.last_mouse_canvas_pos
            self._update_extended_crosshair(x, y)

        self._update_zoom_extended_crosshair()

    def _update_extended_crosshair(self, x: float, y: float) -> None:
        length = self.extended_crosshair_length.get()

        if not self.extended_crosshair_ids:
            hline_id = self.canvas.create_line(
                x - length,
                y,
                x + length,
                y,
                fill="lime",
                width=1,
                tags="extended_crosshair",
            )
            vline_id = self.canvas.create_line(
                x,
                y - length,
                x,
                y + length,
                fill="lime",
                width=1,
                tags="extended_crosshair",
            )
            self.extended_crosshair_ids = [hline_id, vline_id]
        else:
            hline_id, vline_id = self.extended_crosshair_ids
            self.canvas.coords(hline_id, x - length, y, x + length, y)
            self.canvas.coords(vline_id, x, y - length, x, y + length)

        for item_id in self.extended_crosshair_ids:
            self.canvas.tag_raise(item_id)

    def _hide_extended_crosshair(self) -> None:
        for item_id in self.extended_crosshair_ids:
            try:
                self.canvas.delete(item_id)
            except Exception as e:
                logger.warning(f"Failed to delete extended crosshair item: {e}")
        self.extended_crosshair_ids = []

    # Enables/disables the hover circle UI and hides it when disabled.
    def _toggle_hover(self) -> None:
        enabled = self.hover_enabled.get()
        self.radius_scale.config(state="normal" if enabled else "disabled")
        if enabled and self.femoral_axis_enabled.get():
            self.femoral_axis_enabled.set(False)
            self.femoral_axis_count_scale.config(state="disabled")
            self.femoral_axis_whisker_tip_length_scale.config(state="disabled")
            self._clear_femoral_axis_overlay()
        if not enabled:
            self._hide_hover_circle()

    # Keeps the hover circle radius in range and updates it live.
    def _on_radius_change(self, _value: str) -> None:
        if not self.hover_enabled.get():
            return
        r = max(1, min(300, self.hover_radius.get()))
        self.hover_radius.set(r)
        if self.hover_circle_id is not None:
            x0, y0, x1, y1 = self.canvas.coords(self.hover_circle_id)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            self._update_hover_circle(cx, cy)

    # Moves the hover circle with the mouse within image bounds.
    def _on_mouse_move(self, event) -> None:
        if not self.current_image:
            self.last_mouse_canvas_pos = None
            self._clear_line_preview()
            self._clear_femoral_axis_overlay()
            self._hide_mouse_crosshair()
            self._update_zoom_view(None, None)
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()
            return
        x0, y0, x1, y1 = self._display_rect()
        if x0 <= event.x < x1 and y0 <= event.y < y1:
            self.last_mouse_canvas_pos = (event.x, event.y)
            self._update_mouse_crosshair(event.x, event.y)
            self._update_zoom_view(event.x, event.y)
            self._update_line_preview(event.x, event.y)
            self._update_femoral_axis_overlay()
            if self.hover_enabled.get():
                self._update_hover_circle(
                    event.x, event.y
                )  # hover circle stays screen-space
            else:
                self._hide_hover_circle()
            if self.extended_crosshair_enabled.get():
                self._update_extended_crosshair(event.x, event.y)
            else:
                self._hide_extended_crosshair()
        else:
            self.last_mouse_canvas_pos = None
            self._clear_line_preview()
            self._clear_femoral_axis_overlay()
            self._hide_mouse_crosshair()
            self._hide_hover_circle()
            self._update_zoom_view(None, None)
            self._hide_extended_crosshair()
            self._hide_zoom_extended_crosshair()

    def _on_canvas_leave(self, _event) -> None:
        self._hide_hover_circle()
        self._clear_femoral_axis_overlay()
        self._hide_extended_crosshair()
        self._hide_mouse_crosshair()
        self._clear_line_preview()
        self.last_mouse_canvas_pos = None
        self._update_zoom_view(None, None)
        self._hide_zoom_extended_crosshair()

    # Adjusts hover radius via standard mouse wheel events.
    def _on_mousewheel(self, event) -> None:
        if self.right_mouse_held:
            step = 2 if event.delta > 0 else -2
            self._change_zoom_percent(step)
            return
        if self.femoral_axis_enabled.get() and self.selected_landmark.get() in (
            "L-FA",
            "R-FA",
        ):
            step = 2 if event.delta > 0 else -2
            self._change_femoral_axis_length(step)
            return
        if not self.hover_enabled.get():
            return
        step = 2 if event.delta > 0 else -2
        self._change_radius(step)

    # Adjusts hover radius for Linux button-4/5 events.
    def _on_scroll_linux(self, direction: int) -> None:
        if self.right_mouse_held:
            step = 2 if direction > 0 else -2
            self._change_zoom_percent(step)
            return
        if self.femoral_axis_enabled.get() and self.selected_landmark.get() in (
            "L-FA",
            "R-FA",
        ):
            step = 2 if direction > 0 else -2
            self._change_femoral_axis_length(step)
            return
        if not self.hover_enabled.get():
            return
        step = 2 if direction > 0 else -2
        self._change_radius(step)

    # Changes the hover radius and triggers a redraw if it changed.
    def _change_radius(self, delta: int) -> None:
        new_r = max(1, min(300, self.hover_radius.get() + delta))
        if new_r != self.hover_radius.get():
            self.hover_radius.set(new_r)
            self._on_radius_change(str(new_r))

    # Creates or updates the hover circle at the given position.
    def _update_hover_circle(self, x, y) -> None:
        r = self.hover_radius.get()
        x0, y0, x1, y1 = x - r, y - r, x + r, y + r
        if self.hover_circle_id is None:
            self.hover_circle_id = self.canvas.create_oval(
                x0, y0, x1, y1, outline="cyan", width=1, tags="hover_circle"
            )
        else:
            self.canvas.coords(self.hover_circle_id, x0, y0, x1, y1)

    def _update_mouse_crosshair(self, x: float, y: float) -> None:
        circle_r = 8
        cross_r = 4

        if not self.mouse_crosshair_ids:
            circle_id = self.canvas.create_oval(
                x - circle_r,
                y - circle_r,
                x + circle_r,
                y + circle_r,
                outline="cyan",
                width=1,
                tags="mouse_crosshair",
            )
            hline_id = self.canvas.create_line(
                x - cross_r,
                y,
                x + cross_r,
                y,
                fill="cyan",
                width=1,
                tags="mouse_crosshair",
            )
            vline_id = self.canvas.create_line(
                x,
                y - cross_r,
                x,
                y + cross_r,
                fill="cyan",
                width=1,
                tags="mouse_crosshair",
            )
            self.mouse_crosshair_ids = [circle_id, hline_id, vline_id]
        else:
            circle_id, hline_id, vline_id = self.mouse_crosshair_ids
            self.canvas.coords(
                circle_id,
                x - circle_r,
                y - circle_r,
                x + circle_r,
                y + circle_r,
            )
            self.canvas.coords(hline_id, x - cross_r, y, x + cross_r, y)
            self.canvas.coords(vline_id, x, y - cross_r, x, y + cross_r)

        for item_id in self.mouse_crosshair_ids:
            self.canvas.tag_raise(item_id)

    def _hide_mouse_crosshair(self) -> None:
        for item_id in self.mouse_crosshair_ids:
            self.canvas.delete(item_id)
        self.mouse_crosshair_ids = []

    def _on_right_button_press(self, event) -> None:
        self.right_mouse_held = True

    def _on_right_button_release(self, event) -> None:
        self.right_mouse_held = False

    # Deletes the hover circle if present.
    def _hide_hover_circle(self) -> None:
        if self.hover_circle_id is not None:
            self.canvas.delete(self.hover_circle_id)
            self.hover_circle_id = None

    # Clears all segmentation overlays and connector lines.
    def _remove_all_overlays(self):
        for lm in list(self.seg_item_ids.keys()):
            try:
                self.canvas.delete(self.seg_item_ids[lm])
            except Exception as e:
                logger.warning(f"Failed to delete overlay for {lm}: {e}")
        self.seg_item_ids.clear()
        self.seg_img_objs.clear()
        self._remove_pair_lines()

    # Removes a specific landmark's overlay from the canvas.
    def _remove_overlay_for(self, lm: str) -> None:
        if lm in self.seg_item_ids:
            try:
                self.canvas.delete(self.seg_item_ids[lm])
            except Exception as e:
                logger.warning(f"Failed to delete overlay for {lm}: {e}")
            self.seg_item_ids.pop(lm, None)
            self.seg_img_objs.pop(lm, None)

    # Shows or hides a landmark overlay depending on mask and visibility.
    def _update_overlay_for(self, lm: str) -> None:
        vis = True
        vis_var = self.landmark_visibility.get(lm)
        if vis_var is not None:
            vis = bool(vis_var.get())
        has_mask = (
            self.current_image_path
            and str(self.current_image_path) in self.seg_masks
            and lm in self.seg_masks[str(self.current_image_path)]
        )
        if not has_mask or not vis:
            self._remove_overlay_for(lm)
            return
        mask = self.seg_masks[str(self.current_image_path)][lm]
        # self._render_overlay_for(lm, mask)
        self.canvas.tag_raise("marker")

    # Renders a semi-transparent RGBA overlay from a binary mask.
    def _render_overlay_for(
        self,
        lm: str,
        mask: np.ndarray,
        fill_rgba: Tuple[int, int, int, int] = (0, 255, 255, 120),
    ) -> None:
        if mask is None or self.current_image is None:
            return

        # Ensure transform is current
        if self.disp_size == (0, 0):
            self._recompute_transform()

        disp_w, disp_h = self.disp_size
        off_x, off_y = self.disp_off

        mask_u8 = (mask > 0).astype(np.uint8) * 255
        mask_img = Image.fromarray(mask_u8, mode="L").resize(
            (disp_w, disp_h), Image.Resampling.NEAREST
        )

        overlay = Image.new("RGBA", (disp_w, disp_h), (0, 0, 0, 0))
        color_img = Image.new("RGBA", (disp_w, disp_h), fill_rgba)

        overlay.paste(color_img, (0, 0), mask_img)

        self.seg_img_objs[lm] = ImageTk.PhotoImage(overlay)

        if lm not in self.seg_item_ids:
            self.seg_item_ids[lm] = self.canvas.create_image(
                off_x, off_y, anchor="nw", image=self.seg_img_objs[lm], tags=f"seg_{lm}"
            )
        else:
            self.canvas.itemconfigure(
                self.seg_item_ids[lm], image=self.seg_img_objs[lm]
            )
            self.canvas.coords(self.seg_item_ids[lm], off_x, off_y)

        self.canvas.tag_lower(self.seg_item_ids[lm], "marker")
        self.canvas.tag_raise("marker")

    # Handles click to place a landmark and optionally run LOB/ROB segmentation.
    def _on_left_press(self, event) -> None:
        x0, y0, x1, y1 = self._display_rect()
        if not self.current_image:
            return
        if not (x0 <= event.x < x1 and y0 <= event.y < y1):
            return

        self.last_mouse_canvas_pos = (event.x, event.y)
        self._update_mouse_crosshair(event.x, event.y)
        self._update_zoom_view(event.x, event.y)

        lm = self.selected_landmark.get()
        if not lm:
            messagebox.showwarning(
                "No Landmark", "Please select a landmark in the list."
            )
            return

        xi, yi = self._screen_to_img(event.x, event.y)
        x, y = self._clamp_img_point(xi, yi)

        if self._is_line_landmark(lm):
            hit_idx = self._find_line_point_hit(lm, event.x, event.y)
            if hit_idx is not None:
                self.dragging_landmark = lm
                self.dragging_point_index = hit_idx
                self.dragging_line_whole = False
                self.dragging_line_last_img_pos = None
                return

            pts = self._get_line_points(lm)
            if len(pts) == 2 and self._is_line_hit(lm, event.x, event.y):
                self.dragging_landmark = lm
                self.dragging_point_index = None
                self.dragging_line_whole = True
                self.dragging_line_last_img_pos = (x, y)
                return

            if len(pts) == 0:
                if not self._check_left_right_order_for_landmark(lm, x, y):
                    return
                self._set_line_points(lm, [(x, y)])
            elif len(pts) == 1:
                mean_x = (pts[0][0] + x) / 2.0
                if not self._check_left_right_order_for_landmark(lm, mean_x, y):
                    return
                self._set_line_points(lm, [pts[0], (x, y)])
                self._clear_line_preview()
            else:
                if not self._check_left_right_order_for_landmark(lm, x, y):
                    return
                self._set_line_points(lm, [(x, y)])
                self._clear_line_preview()

            self._draw_points()
            self._refresh_zoom_landmark_overlay()
            self.dirty = True
            self._auto_save_to_db()
            return

        if not self._check_left_right_order_for_landmark(lm, x, y):
            return

        self.annotations.setdefault(str(self.current_image_path), {})[lm] = (x, y)
        if lm in self.landmark_found:
            self.landmark_found[lm].set(True)
        self._draw_points()
        self._refresh_zoom_landmark_overlay()
        self.dirty = True
        if lm in ("LOB", "ROB"):
            if cv2 is None:
                messagebox.showerror(
                    "OpenCV missing",
                    'cv2 is not available. Install with "pip install opencv-python".',
                )
                return
            self.last_seed[lm] = (int(x), int(y))
            self._store_current_settings_for(lm)
            self._resegment_for(lm)
        # Auto-save to database immediately after placing landmark
        self._auto_save_to_db()
        return

    def _check_left_right_order_for_landmark(
        self,
        lm: str,
        new_x: float,
        new_y: float,
    ) -> bool:
        if lm.startswith("L-"):
            other_lm = "R-" + lm[2:]
            is_left_landmark = True
        elif lm.startswith("R-"):
            other_lm = "L-" + lm[2:]
            is_left_landmark = False
        else:
            return True

        allowed = self._get_allowed_landmarks_for_current_view()
        if other_lm not in allowed:
            return True

        pts, _quality = self._get_annotations()
        if other_lm not in pts:
            return True

        # Use x-position of the already-placed corresponding landmark.
        # For line landmarks, use the mean x of the existing line points.
        if self._is_line_landmark(other_lm):
            other_pts = self._get_line_points(other_lm)
            if not other_pts:
                return True
            other_x = sum(px for px, _py in other_pts) / len(other_pts)
        else:
            other_pt = pts[other_lm]
            if isinstance(other_pt, tuple):
                other_x = float(other_pt[0])
            else:
                return True

        is_pa = self.current_image_direction == "PA"

        if is_left_landmark:
            if is_pa:
                is_valid = new_x < other_x
                side_word = "LEFT"
            else:
                is_valid = new_x > other_x
                side_word = "RIGHT"
            bad_msg = (
                f'"{lm}" must be to the {side_word} of "{other_lm}" '
                f"({self.current_image_direction} image).\n\n"
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
                f"({self.current_image_direction} image).\n\n"
                f"Current click x = {new_x:.1f}\n"
                f"{other_lm} x = {other_x:.1f}"
            )

        if not is_valid:
            messagebox.showwarning("Left/Right Landmark Order", bad_msg)
            return False

        return True

    def _on_left_drag(self, event) -> None:
        if not self.current_image:
            return

        self.last_mouse_canvas_pos = (event.x, event.y)
        self._update_mouse_crosshair(event.x, event.y)

        if self.extended_crosshair_enabled.get():
            self._update_extended_crosshair(event.x, event.y)
        else:
            self._hide_extended_crosshair()

        self._update_zoom_view(event.x, event.y)

        if self.hover_enabled.get():
            self._update_hover_circle(event.x, event.y)
        else:
            self._hide_hover_circle()

        x0, y0, x1, y1 = self._display_rect()
        if not (x0 <= event.x < x1 and y0 <= event.y < y1):
            return

        xi, yi = self._screen_to_img(event.x, event.y)
        x, y = self._clamp_img_point(xi, yi)

        if self.dragging_landmark is None:
            return

        pts = self._get_line_points(self.dragging_landmark)
        if not pts:
            return

        if self.dragging_point_index is not None:
            if self.dragging_point_index >= len(pts):
                return

            pts[self.dragging_point_index] = (x, y)
            self._set_line_points(self.dragging_landmark, pts)
            self._draw_points()
            self._refresh_zoom_landmark_overlay()
            self.dirty = True
            return

        if self.dragging_line_whole:
            if len(pts) != 2:
                return

            if self.dragging_line_last_img_pos is None:
                self.dragging_line_last_img_pos = (x, y)
                return

            last_x, last_y = self.dragging_line_last_img_pos
            dx = x - last_x
            dy = y - last_y

            if abs(dx) < 1e-12 and abs(dy) < 1e-12:
                return

            new_pts = []
            for px, py in pts:
                nx, ny = self._clamp_img_point(px + dx, py + dy)
                new_pts.append((nx, ny))

            actual_dx = new_pts[0][0] - pts[0][0]
            actual_dy = new_pts[0][1] - pts[0][1]
            new_pts = [
                self._clamp_img_point(px + actual_dx, py + actual_dy) for px, py in pts
            ]

            self._set_line_points(self.dragging_landmark, new_pts)
            self.dragging_line_last_img_pos = (x, y)
            self._draw_points()
            self._refresh_zoom_landmark_overlay()
            self.dirty = True

    def _on_left_release(self, event) -> None:
        x0, y0, x1, y1 = self._display_rect()
        if self.current_image and x0 <= event.x < x1 and y0 <= event.y < y1:
            self.last_mouse_canvas_pos = (event.x, event.y)
            self._update_mouse_crosshair(event.x, event.y)
            self._update_zoom_view(event.x, event.y)
            self._update_line_preview(event.x, event.y)

        if self.dragging_landmark is not None:
            self.dragging_landmark = None
            self.dragging_point_index = None
            self.dragging_line_whole = False
            self.dragging_line_last_img_pos = None
            self._auto_save_to_db()

    def _delete_current_landmark(self) -> None:
        """
        The goal of this function is to remove the annotation from the current landmark. When saving. I'm going to make.
        """
        lm = self.selected_landmark.get()
        if not lm:
            messagebox.showwarning(
                "No Landmark", "Please select a landmark in the list"
            )
            return

        current_pts = self.annotations.setdefault(str(self.current_image_path), {})
        if lm in current_pts:
            # Delete it if it does
            del current_pts[lm]

        if self._is_line_landmark(lm):
            self._clear_line_preview()

        self._draw_points()
        self._refresh_zoom_landmark_overlay()
        self.dirty = True
        if lm in ("LOB", "ROB"):
            if cv2 is None:
                messagebox.showerror(
                    "OpenCV missing",
                    'cv2 is not available. Install with "pip install opencv-python".',
                )
                return
            self._store_current_settings_for(lm)
            self._resegment_for(lm)
        # Auto-save to database immediately after deleting landmark
        self._auto_save_to_db()
        return

    # Triggers re-segmentation if the selected landmark is LOB/ROB.
    def _resegment_selected_if_needed(self) -> None:
        lm = self.selected_landmark.get()
        if lm in ("LOB", "ROB"):
            self._store_current_settings_for(lm)
            self._resegment_for(lm)

    # Runs the chosen segmentation method for a landmark and updates overlay.
    def _resegment_for(self, lm: str, apply_saved_settings: bool = False) -> None:
        if self.current_image_path is None:
            return
        seed = self.last_seed.get(lm)
        if seed is None or cv2 is None or self.current_image is None:
            return
        x, y = seed
        mask = self._segment_with_fallback(x, y, lm)

        if mask is None:
            return
        mask = self._grow_shrink(mask, self.grow_shrink.get())
        self.seg_masks.setdefault(str(self.current_image_path), {})[lm] = mask
        self._update_overlay_for(lm)

    def _segment_with_fallback(self, x: int, y: int, lm: str) -> np.ndarray | None:
        return None

    # Converts image to preprocessed grayscale (CLAHE + blur).
    def _preprocess_gray(self):
        img_rgb = np.array(self.current_image)
        if img_rgb.shape[-1] == 3:
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_rgb

        if self.use_clahe.get():
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        return gray

    # Segments a region via flood fill with optional edge-lock barrier.
    def _segment_ff(self, x: int, y: int) -> np.ndarray | None:
        gray = self._preprocess_gray()
        h, w = gray.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return None
        barrier = np.zeros((h, w), np.uint8)
        if self.edge_lock.get():
            edges = cv2.Canny(gray, 40, 120)
            k = max(1, min(5, int(self.edge_lock_width.get())))
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)
            )
            barrier = cv2.dilate(edges, kernel, iterations=1)
            barrier = (barrier > 0).astype(np.uint8)
        ff_mask = np.zeros((h + 2, w + 2), np.uint8)
        ff_mask[0, :], ff_mask[-1, :], ff_mask[:, 0], ff_mask[:, -1] = 1, 1, 1, 1
        if self.edge_lock.get():
            ff_mask[1:-1, 1:-1][barrier == 1] = 1
        sens = int(self.fill_sensitivity.get())
        tol = max(1, min(80, 2 * sens + 2))
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
        region = self._sanity_and_clean(region)
        return region

    # Segments a region via adaptive thresholding and connected components.
    def _segment_adaptive_cc(self, x: int, y: int) -> np.ndarray | None:
        gray = self._preprocess_gray()
        h, w = gray.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return None
        sens = int(self.fill_sensitivity.get())
        block = max(11, 2 * (5 + sens // 2) + 1)
        C = max(2, min(15, 12 - sens // 5))
        thr = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, C
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
        region = self._sanity_and_clean(region)
        return region

    # Rejects implausible masks and performs a closing for cleanup.
    def _sanity_and_clean(self, mask: np.ndarray) -> np.ndarray | None:
        h, w = mask.shape[:2]
        area = int(mask.sum())
        if area < 30:
            return None
        if area > 0.7 * w * h:
            return None
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel2, iterations=1)
        return (mask > 0).astype(np.uint8)

    # Dilates (positive) or erodes (negative) a mask by the requested steps.
    def _grow_shrink(self, mask: np.ndarray, steps: int) -> np.ndarray:
        if steps == 0:
            return (mask > 0).astype(np.uint8)
        k = min(25, max(1, abs(steps)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        if steps > 0:
            out = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1)
        else:
            out = cv2.erode(mask.astype(np.uint8), kernel, iterations=1)
        return (out > 0).astype(np.uint8)

    # Returns a dict of the current UI segmentation settings.
    def _current_settings_dict(self) -> Dict:
        return {
            "method": self.method.get(),
            "sens": int(self.fill_sensitivity.get()),
            "edge_lock": 1 if self.edge_lock.get() else 0,
            "edge_width": int(self.edge_lock_width.get()),
            "clahe": 1 if self.use_clahe.get() else 0,
            "grow": int(self.grow_shrink.get()),
        }

    # Stores current UI settings for a specific landmark on this image.
    def _store_current_settings_for(self, lm: str) -> None:
        per_img = self.lm_settings.setdefault(str(self.current_image_path), {})
        per_img[lm] = self._current_settings_dict()

    # Applies saved settings for a landmark back into the UI controls.
    def _apply_settings_to_ui_for(self, lm: str) -> None:
        st = self.lm_settings.get(str(self.current_image_path), {}).get(lm)
        if not st:
            return
        self.method.set(st["method"])
        try:
            self.fill_sensitivity.set(int(st["sens"]))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to apply sensitivity setting for {lm}: {e}")
        try:
            self.edge_lock.set(bool(int(st["edge_lock"])))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to apply edge_lock setting for {lm}: {e}")
        try:
            self.edge_lock_width.set(int(st["edge_width"]))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to apply edge_width setting for {lm}: {e}")
        try:
            self.use_clahe.set(bool(int(st["clahe"])))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to apply clahe setting for {lm}: {e}")
        try:
            self.grow_shrink.set(int(st["grow"]))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to apply grow setting for {lm}: {e}")

    # Toggle visibility.
    def _set_selected_visibility(self, visible: bool) -> None:
        lm = self.selected_landmark.get()
        if not lm:
            return
        var = self.landmark_visibility.get(lm)
        if var is None:
            return
        var.set(visible)
        self._draw_points()

    def _on_arrow_left(self, event) -> None:
        self._set_selected_visibility(False)

    def _on_arrow_right(self, event) -> None:
        self._set_selected_visibility(True)

    def _format_shortcuts(
        self,
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

    def _on_h_press(self, event=None) -> None:
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
        help_text = self._format_shortcuts(
            shortcuts,
            width=60,
            leader=".",
        )

        win = tk.Toplevel(self)
        win.title("Help & Keyboard Shortcuts")
        win.transient(self)
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(
            frm,
            text="Keyboard Shortcuts",
            font=self.heading_font,
        ).pack(anchor="w", pady=(0, 8))

        text = tk.Text(
            frm,
            wrap="none",
            height=len(shortcuts) + 1,
            borderwidth=0,
            highlightthickness=0,
        )
        text.pack(fill="both", expand=True)

        text.configure(font=self.dialogue_font)

        text.insert("1.0", help_text)
        text.configure(state="disabled")

        ttk.Button(
            frm,
            text="Close",
            command=win.destroy,
        ).pack(anchor="e", pady=(10, 0))

    def _open_landmark_reference(self, event=None) -> None:
        """Open or focus the landmark reference popup."""
        if self._landmark_ref is None:
            return

        if self._landmark_ref_dialog is not None:
            try:
                self._landmark_ref_dialog.lift()
                self._landmark_ref_dialog.focus_force()
                return
            except tk.TclError:
                # Window was destroyed outside our tracking
                self._landmark_ref_dialog = None

        self._landmark_ref_dialog = LandmarkReferenceDialog(
            parent=self,
            reference=self._landmark_ref,
            current_landmark=self.selected_landmark.get() or None,
            on_close=self._on_landmark_ref_dialog_closed,
        )

    def _on_landmark_ref_dialog_closed(self) -> None:
        """Clear the dialog reference when the popup is closed."""
        self._landmark_ref_dialog = None

    def _configure_linux_fonts(self) -> None:
        # (optional) scaling tweak, only on Linux
        self.tk.call("tk", "scaling", 1.25)

        # Pick whatever you decided works well in your env
        self.heading_font = tkfont.Font(
            family="Liberation Sans", size=15, weight="bold"
        )
        self.dialogue_font = tkfont.Font(
            family="Liberation Sans", size=12, weight="bold"
        )

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
        style = ttk.Style(self)
        style.theme_use(style.theme_use())  # force theme init / refresh

        style.configure(".", font=self.dialogue_font)
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
            style.configure(s, font=self.dialogue_font)
        return

    def _refresh_image_listbox(self) -> None:
        if self.image_tree is None:
            return

        self._suspend_image_tree_select = True
        try:
            for item in self.image_tree.get_children():
                self.image_tree.delete(item)

            for idx, path in enumerate(self.images):
                progress = self._image_progress_text(path)
                self.image_tree.insert(
                    "",
                    "end",
                    iid=str(idx),
                    values=(extract_filename(path), progress),
                    tags=("done",) if self._image_progress_done(path) else (),
                )

            self.image_tree.tag_configure("done", foreground="green")

            if 0 <= self.current_image_index < len(self.images):
                iid = str(self.current_image_index)
                if self.image_tree.exists(iid):
                    self.image_tree.selection_set(iid)
                    self.image_tree.focus(iid)
                    self.image_tree.see(iid)
            else:
                self.image_tree.selection_remove(self.image_tree.selection())
        finally:
            if not getattr(self, "_navigation_in_progress", False):
                self._suspend_image_tree_select = False

    def _on_image_list_select(self, _event=None) -> None:
        if self.image_tree is None or getattr(
            self, "_suspend_image_tree_select", False
        ):
            return

        selection = self.image_tree.selection()
        if not selection:
            return

        idx = int(selection[0])
        if idx == self.current_image_index or not (0 <= idx < len(self.images)):
            return

        self._navigation_in_progress = True
        self._suspend_image_tree_select = True
        try:
            if not self._maybe_save_before_destructive_action("switch images"):
                self._refresh_image_listbox()
                return

            self.current_image_index = idx
            self.load_image_from_path(self.images[idx])
        finally:
            self._navigation_in_progress = False
            self._suspend_image_tree_select = False

    def _count_allowed_landmarks_for_current_image(self, image_path: Path) -> int:
        key = self._path_key(image_path)
        idx = self.image_index_map.get(key)
        if idx is None:
            return 0

        if (
            self.current_image_path is not None
            and self._path_key(self.current_image_path) == key
        ):
            view = self.current_view_var.get().strip()
        else:
            record = self.json_data["images"][idx]
            view = record.get("view")

        if not view or view not in self.allowed_views:
            return 0

        return len(self.allowed_views.get(view, []))

    def _count_completed_landmarks_for_current_image(self, image_path: Path) -> int:
        key = self._path_key(image_path)
        idx = self.image_index_map.get(key)
        if idx is None:
            return 0

        is_current_image = (
            self.current_image_path is not None
            and self._path_key(self.current_image_path) == key
        )
        if is_current_image:
            view = self.current_view_var.get().strip()
            annotations = self.annotations.get(key, {}) or {}
            allowed = (
                set(self.allowed_views.get(view, []))
                if view and view in self.allowed_views
                else set(annotations.keys())
            )
            return sum(1 for lm in allowed if annotations.get(lm) is not None)

        record = self.json_data["images"][idx]
        view = record.get("view")
        annotations = record.get("annotations", {}) or {}

        if view and view in self.allowed_views:
            allowed = set(self.allowed_views.get(view, []))
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

    def _image_progress_text(self, image_path: Path) -> str:
        key = self._path_key(image_path)
        idx = self.image_index_map.get(key)
        if idx is None:
            return "0/?"

        if (
            self.current_image_path is not None
            and self._path_key(self.current_image_path) == key
        ):
            view = self.current_view_var.get().strip()
        else:
            record = self.json_data["images"][idx]
            view = record.get("view")

        done = self._count_completed_landmarks_for_current_image(image_path)

        if not view or view not in self.allowed_views:
            return f"{done}/?"

        total = self._count_allowed_landmarks_for_current_image(image_path)
        return f"{done}/{total}"

    def _image_progress_done(self, image_path: Path) -> bool:
        key = self._path_key(image_path)
        idx = self.image_index_map.get(key)
        if idx is None:
            return False

        if (
            self.current_image_path is not None
            and self._path_key(self.current_image_path) == key
        ):
            view = self.current_view_var.get().strip()
        else:
            record = self.json_data["images"][idx]
            view = record.get("view")

        if not view or view not in self.allowed_views:
            return False

        done = self._count_completed_landmarks_for_current_image(image_path)
        total = self._count_allowed_landmarks_for_current_image(image_path)
        return total > 0 and done >= total

    def _widget_y_in_inner(self, widget) -> int:
        y = 0
        w = widget
        while w is not None and w is not self.lp_inner:
            y += w.winfo_y()
            parent_name = w.winfo_parent()
            if not parent_name:
                break
            w = w.nametowidget(parent_name)
        return y

    def _get_csv_images_from_directory(self, dir: Path) -> list[Path]:
        try:
            df = pd.read_csv(self.abs_csv_path)
        except Exception:
            return []

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT image_filename FROM annotations WHERE verified = 0"
                )
                rows = cursor.fetchall()
        except sqlite3.Error:
            return []

        csv_files = [elem[0] for elem in rows if elem is not None]

        local_dir_csv_files = []
        for root, dirs, files in dir.walk():
            for file in files:
                if file in csv_files:
                    local_dir_csv_files.append(Path(root / file))

        return local_dir_csv_files

    def _find_unannotated_images(self) -> None:
        """Scan directory for images not in CSV, enter queue mode."""
        if not hasattr(self, "abs_csv_path") or not self.abs_csv_path:
            messagebox.showwarning(
                "No CSV", "Please load a CSV file first (Load CSV button)"
            )
            return

        # Select directory to scan
        scan_dir = filedialog.askdirectory(
            initialdir=BASE_DIR, title="Select folder to scan for unannotated images"
        )

        if not scan_dir:
            return

        scan_path = Path(scan_dir)

        # Load existing annotations from CSV
        try:
            df = pd.read_csv(self.abs_csv_path)
            col = self._detect_path_column(df)

            # Build a set of files that are "truly annotated"
            # (either have landmarks OR have been quality-rated as bad)
            annotated_filenames: Set = set()

            for _, row in df.iterrows():
                # filename = Path(str(row[col])).name.lower()
                filename = extract_filename(row[col])

                # Check if any landmark columns have values
                has_landmarks = any(
                    pd.notna(row.get(lm)) and str(row.get(lm, "")).strip()
                    for lm in self.landmarks
                )

                # Check image quality
                quality = row.get("image_quality", 0)
                try:
                    quality = int(quality)
                except (ValueError, TypeError):
                    quality = 0

                # Consider "annotated" if:
                # 1. Has landmarks, OR
                # 2. Has no landmarks but quality != 0 (marked as bad image)
                if has_landmarks or quality != 0:
                    annotated_filenames.add(filename)

        except Exception as e:
            messagebox.showerror("CSV Error", f"Failed to read CSV:\n{e}")
            return

        # Recursively find all image files
        all_images = []
        for dirpath, dirnames, filenames in scan_path.walk():
            if "duplicates" in dirnames:
                dirnames.remove("duplicates")
            for file in filenames:
                if Path(file).suffix.lower() in self.possible_image_suffix:
                    all_images.append(dirpath / file)
                    pass
                pass
            pass

        # Filter to unannotated only
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

        # Sort for consistent ordering
        unannotated.sort()

        # Enter queue mode
        self.unannotated_queue = unannotated
        self.queue_index = 0
        self.queue_mode = True

        # Load first unannotated image
        self.absolute_current_image_path = unannotated[0]
        self.load_image_from_path(unannotated[0])

        self._update_queue_status()

        messagebox.showinfo(
            "Queue Mode",
            f"Found {len(unannotated)} unannotated images.\n\n"
            f"Use Next/Prev (or N/B keys) to cycle through them.\n"
            f"Click 'Exit Queue Mode' to return to normal browsing.",
        )
        self.exit_queue_btn.config(state="normal")
        return

    def _update_queue_status(self) -> None:
        """Update the queue status label."""
        if self.queue_mode and self.unannotated_queue:
            self.queue_status_var.set(
                f"Queue: {self.queue_index + 1} / {len(self.unannotated_queue)} unannotated"
            )
        elif self.check_csv_mode and self.csv_path_queue:
            self.queue_status_var.set(
                f"Queue: {self.csv_index + 1} / {len(self.csv_path_queue)} remaining"
            )
        else:
            self.queue_status_var.set("")

    def _exit_queue_mode(self) -> None:
        """Return to normal directory browsing."""
        self.queue_mode = False
        self.unannotated_queue.clear()
        self.queue_index = 0
        self._update_queue_status()
        self.exit_queue_btn.config(state="disabled")
        messagebox.showinfo("Queue Mode", "Returned to normal directory browsing.")

    def _change_method_to_ff(self) -> None:
        self.use_adap_cc.set(False)
        self.use_ff.set(True)
        self.method.set("Flood Fill")
        return

    def _change_method_to_acc(self) -> None:
        self.use_adap_cc.set(True)
        self.use_ff.set(False)
        self.method.set("Adaptive CC")
        return

    def _check_csv_images(self):
        self.abs_csv_path = filedialog.askopenfilename(
            initialdir=BASE_DIR / "data/csv", filetypes=[("CSV File", ("*.csv"))]
        )
        if self.abs_csv_path:
            df: pd.DataFrame = pd.read_csv(self.abs_csv_path)
            csv_path_column = self._detect_path_column(df)
            self.load_landmarks_from_csv(self.abs_csv_path)
            self.check_csv_mode = True
            if self.csv_local_image_directory_path == None:
                self.csv_local_image_directory_path = filedialog.askdirectory()
            self.csv_path_queue = self._get_csv_images_from_directory(
                Path(self.csv_local_image_directory_path)
            )
            if len(self.csv_path_queue) == 0:
                self.csv_local_image_directory_path = filedialog.askdirectory()

            self.csv_path_queue = self._get_csv_images_from_directory(
                Path(self.csv_local_image_directory_path)
            )

            self.absolute_current_image_path = Path(self.csv_path_queue[0])
            self.load_image_from_path(self.absolute_current_image_path)
            self._update_queue_status()

        return

    def _exit_csv_check_mode(self):
        self.check_csv_mode = False
        self.csv_path_queue.clear()
        self.csv_index = 0
        self.exit_csv_check_btn.config(state="disabled")
        self._update_queue_status()

        return


if __name__ == "__main__":
    # Feature 1 change
    # Feature 2 change
    # Testing Tags
    app = AnnotationGUI()
    print(app._get_protocol_version())
    app.option_add("*Label.font", "helvetica 20 bold")
    app.mainloop()
