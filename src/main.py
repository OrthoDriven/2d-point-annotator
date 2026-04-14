from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingTypeArgument=false, reportUninitializedInstanceVariable=false, reportOperatorIssue=false, reportAttributeAccessIssue=false, reportImportCycles=false
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
from typing import Dict, List, Optional, Set, Tuple, Union, cast

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
from dataset_config import (  # pyright: ignore[reportImplicitRelativeImport]
    get_data_dir,
    get_dataset_dest,
    load_datasets_config,
)
from dirs import BASE_DIR, PLATFORM  # pyright: ignore[reportImplicitRelativeImport]
from downloader import download_dataset  # pyright: ignore[reportImplicitRelativeImport]
from landmark_reference import (  # pyright: ignore[reportImplicitRelativeImport]
    LandmarkReference,  # pyright: ignore[reportImplicitRelativeImport]
)
from landmark_reference_dialog import (  # pyright: ignore[reportImplicitRelativeImport]
    LandmarkReferenceDialog,  # pyright: ignore[reportImplicitRelativeImport]
)
from geometry import (  # pyright: ignore[reportImplicitRelativeImport]
    img_to_screen,
    screen_to_img,
    display_rect,
    clamp_img_point,
    point_to_segment_distance_px,
    is_line_landmark,
)
from path_utils import extract_filename  # pyright: ignore[reportImplicitRelativeImport]
from segmentation import (  # pyright: ignore[reportImplicitRelativeImport]
    preprocess_gray,
    segment_ff,
    segment_adaptive_cc,
    sanity_and_clean,
    grow_shrink,
)
from data_io import (  # pyright: ignore[reportImplicitRelativeImport]
    parse_annotations_for_record,
    init_database,
    db_is_populated,
)
from navigation import (  # pyright: ignore[reportImplicitRelativeImport]
    get_image_index_from_directory,
    detect_path_column,
)
from ui_builder import build_ui  # pyright: ignore[reportImplicitRelativeImport]
from zoom_render import (  # pyright: ignore[reportImplicitRelativeImport]
    get_zoom_canvas_size,
    render_black_zoom_view,
    update_zoom_view,
    on_zoom_change,
    change_zoom_percent,
    update_zoom_crosshair,
    hide_zoom_crosshair,
    update_zoom_extended_crosshair,
    hide_zoom_extended_crosshair,
    refresh_zoom_landmark_overlay,
    clear_zoom_landmark_overlay,
)
from canvas_render import (  # pyright: ignore[reportImplicitRelativeImport]
    clear_line_preview,
    draw_points,
    find_landmark_key,
    hide_extended_crosshair,
    hide_hover_circle,
    hide_mouse_crosshair,
    on_extended_crosshair_length_change,
    on_radius_change,
    remove_all_overlays,
    remove_overlay_for,
    remove_pair_lines,
    render_base_image,
    render_overlay_for,
    set_selected_visibility,
    toggle_extended_crosshair,
    toggle_hover,
    update_extended_crosshair,
    update_hover_circle,
    update_line_preview,
    update_mouse_crosshair,
    update_overlay_for,
    update_pair_lines,
)
from canvas_interaction import (  # pyright: ignore[reportImplicitRelativeImport]
    check_left_right_order_for_landmark,
    on_canvas_leave,
    on_canvas_resize,
    on_left_drag,
    on_left_press,
    on_left_release,
    on_mouse_move,
    on_mousewheel,
    on_right_button_press,
    on_right_button_release,
    on_scroll_linux,
)
from document_io import (  # pyright: ignore[reportImplicitRelativeImport]
    apply_settings_to_ui_for,
    auto_save_to_db,
    backup_to_onedrive,
    backup_with_progress_dialog,
    canonical_image_state_for_path,
    change_image_quality as change_image_quality_io,
    current_image_has_unsaved_changes,
    current_image_state_string,
    current_settings_dict,
    export_db_to_csv,
    fire_onedrive_backup,
    get_annotations,
    import_csv_to_db,
    init_onedrive_credentials,
    load_landmarks_from_csv as load_landmarks_from_csv_io,
    load_points as load_points_io,
    maybe_autosave_current_image,
    maybe_save_before_destructive_action,
    prepare_landmark_data,
    refresh_saved_snapshot,
    save_annotations_flow,
    save_json_file,
    schedule_onedrive_backup,
    store_current_settings_for,
    update_path_var,
)
from image_session import (  # pyright: ignore[reportImplicitRelativeImport]
    check_csv_images as session_check_csv_images,
    count_allowed_landmarks as session_count_allowed_landmarks,
    count_completed_landmarks as session_count_completed_landmarks,
    exit_csv_check_mode as session_exit_csv_check_mode,
    exit_queue_mode as session_exit_queue_mode,
    find_unannotated_images as session_find_unannotated_images,
    get_csv_images_from_directory as session_get_csv_images_from_directory,
    get_current_image_record as session_get_current_image_record,
    image_progress_done as session_image_progress_done,
    image_progress_text as session_image_progress_text,
    load_data as session_load_data,
    load_image as session_load_image,
    load_image_from_path as session_load_image_from_path,
    next_image as session_next_image,
    on_close as session_on_close,
    on_image_list_select as session_on_image_list_select,
    prev_image as session_prev_image,
    prompt_for_view_if_needed as session_prompt_for_view_if_needed,
    prune_annotations_for_current_view as session_prune_annotations_for_current_view,
    rebuild_landmark_panel_for_view as session_rebuild_landmark_panel_for_view,
    refresh_image_listbox as session_refresh_image_listbox,
    resolve_image_path as session_resolve_image_path,
    set_current_view as session_set_current_view,
    sync_current_state_to_json_record as session_sync_current_state_to_json_record,
    update_queue_status as session_update_queue_status,
)
from landmark_panel import (  # pyright: ignore[reportImplicitRelativeImport]
    bind_landmark_scroll,
    build_landmark_panel,
    change_selected_landmark,
    delete_current_landmark,
    get_allowed_landmarks_for_current_view,
    get_landmark_flag,
    get_landmark_meta,
    get_landmark_note,
    landmark_mousewheel,
    load_note_for_selected_landmark,
    on_annotated_checkbox_toggled,
    on_arrow_down,
    on_arrow_up,
    on_flag_checkbox_toggled,
    on_image_direction_changed,
    on_landmark_selected,
    on_note_text_modified,
    on_view_selected,
    save_note_for_selected_landmark,
    scroll_landmark_into_view,
    set_all_visibility,
    set_landmark_flag,
    set_landmark_note,
    set_note_editor_enabled,
    update_found_checks,
    widget_y_in_inner,
)
from shortcuts import (  # pyright: ignore[reportImplicitRelativeImport]
    bind_shortcut,
    change_method_to_acc,
    change_method_to_ff,
    change_radius,
    configure_linux_fonts,
    initial_dl_status,
    is_current_image_verified,
    note_text_shortcuts_blocked,
    on_1_press,
    on_2_press,
    on_3_press,
    on_4_press,
    on_arrow_left,
    on_arrow_right,
    on_backspace,
    on_download_data,
    on_h_press,
    on_image_flag_widget_changed,
    on_landmark_ref_dialog_closed,
    on_pg_down,
    on_pg_up,
    on_space,
    open_landmark_reference,
    refresh_image_flag_checkbox_style,
    resegment_for,
    resegment_selected_if_needed,
    sync_auto_tools,
)
from femoral_axis import (  # pyright: ignore[reportImplicitRelativeImport]
    change_femoral_axis_length,
    change_femoral_axis_whisker_tip_length,
    clear_femoral_axis_overlay,
    get_active_femoral_axis_line_screen,
    on_femoral_axis_count_change,
    on_femoral_axis_whisker_tip_length_change,
    toggle_femoral_axis,
    update_femoral_axis_overlay,
)

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
        self.queue_status_var: tk.StringVar
        self.exit_queue_btn: tk.Button
        self.exit_csv_check_btn: tk.Button
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
        on_space(self)

    def _is_current_image_verified(self) -> bool:
        return is_current_image_verified(self)

    def _resolve_image_path(self, raw_path: str) -> Path:
        return session_resolve_image_path(self, raw_path)

    def _path_key(self, path: Union[str, Path]) -> str:
        return str(Path(path).resolve())

    def _get_current_image_record(self) -> Optional[Dict]:
        return session_get_current_image_record(self)

    def _sync_current_state_to_json_record(self) -> None:
        session_sync_current_state_to_json_record(self)

    def _get_allowed_landmarks_for_current_view(self) -> set[str]:
        return get_allowed_landmarks_for_current_view(self)

    def _get_current_view(self) -> str:
        record = self._get_current_image_record()
        if record is None:
            return ""
        val = record.get("view")
        return "" if val is None else str(val)

    def _set_current_view(self, view_name: str) -> None:
        session_set_current_view(self, view_name)

    def _prune_annotations_for_current_view(self) -> None:
        session_prune_annotations_for_current_view(self)

    def _rebuild_landmark_panel_for_view(self) -> None:
        session_rebuild_landmark_panel_for_view(self)

    def _prompt_for_view_if_needed(self) -> None:
        session_prompt_for_view_if_needed(self)

    def _on_view_selected(self, _event=None) -> None:
        on_view_selected(self, _event)

    def _on_image_flag_widget_changed(self) -> None:
        on_image_flag_widget_changed(self)

    def _refresh_image_flag_checkbox_style(self) -> None:
        refresh_image_flag_checkbox_style(self)

    def _on_image_direction_changed(self, _event=None) -> None:
        on_image_direction_changed(self, _event)

    def _save_json_file(self, show_success: bool = False) -> bool:
        return save_json_file(self, show_success)

    def _parse_annotations_for_record(self, record: Dict) -> Dict[str, AnnotationValue]:
        pts, per_img_settings, per_img_meta = parse_annotations_for_record(
            record, self.landmarks, self.line_landmarks
        )
        if self.current_image_path is not None:
            key = self._path_key(self.current_image_path)
            self.lm_settings[key] = per_img_settings
            self.landmark_meta[key] = per_img_meta
        return pts

    def load_data(self) -> None:
        session_load_data(self)

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
        return initial_dl_status(self)

    def _on_download_data(self) -> None:
        on_download_data(self)

    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        build_ui(self)

    def _detect_path_column(self, df: pd.DataFrame) -> str:
        return detect_path_column(df)

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
        return img_to_screen(xi, yi, self.disp_scale, *self.disp_off)

    def _screen_to_img(self, xs: float, ys: float) -> Tuple[float, float]:
        return screen_to_img(xs, ys, self.disp_scale, *self.disp_off)

    def _display_rect(self) -> Tuple[int, int, int, int]:
        return display_rect(self.disp_scale, *self.disp_off, *self.disp_size)

    def _get_zoom_canvas_size(self) -> int:
        return get_zoom_canvas_size(self)

    def _render_black_zoom_view(self) -> None:
        render_black_zoom_view(self)

    def _update_zoom_view(
        self, mouse_x: float | None = None, mouse_y: float | None = None
    ) -> None:
        update_zoom_view(self, mouse_x, mouse_y)

    def _on_zoom_change(self, _value: str) -> None:
        on_zoom_change(self, _value)

    def _change_zoom_percent(self, delta: int) -> None:
        change_zoom_percent(self, delta)

    def _update_zoom_crosshair(self) -> None:
        update_zoom_crosshair(self)

    def _hide_zoom_crosshair(self) -> None:
        hide_zoom_crosshair(self)

    def _update_zoom_extended_crosshair(self) -> None:
        update_zoom_extended_crosshair(self)

    def _hide_zoom_extended_crosshair(self) -> None:
        hide_zoom_extended_crosshair(self)

    def _change_femoral_axis_length(self, delta: int) -> None:
        change_femoral_axis_length(self, delta)  # pyright: ignore[reportArgumentType]

    def _toggle_femoral_axis(self) -> None:
        toggle_femoral_axis(self)  # pyright: ignore[reportArgumentType]

    def _on_femoral_axis_whisker_tip_length_change(self, _value: str) -> None:
        on_femoral_axis_whisker_tip_length_change(self, _value)  # pyright: ignore[reportArgumentType]

    def _on_femoral_axis_count_change(self, _value: str) -> None:
        on_femoral_axis_count_change(self, _value)  # pyright: ignore[reportArgumentType]

    def _clear_femoral_axis_overlay(self) -> None:
        clear_femoral_axis_overlay(self)  # pyright: ignore[reportArgumentType]

    def _change_femoral_axis_whisker_tip_length(self, delta: int) -> None:
        change_femoral_axis_whisker_tip_length(self, delta)  # pyright: ignore[reportArgumentType]

    def _get_active_femoral_axis_line_screen(
        self,
    ) -> Optional[Tuple[float, float, float, float]]:
        return get_active_femoral_axis_line_screen(self)  # pyright: ignore[reportArgumentType]

    def _update_femoral_axis_overlay(self) -> None:
        update_femoral_axis_overlay(self)  # pyright: ignore[reportArgumentType]

    def _clear_zoom_landmark_overlay(self) -> None:
        clear_zoom_landmark_overlay(self)

    def _is_line_landmark(self, lm: str) -> bool:
        return is_line_landmark(lm, self.line_landmarks)

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
        return clamp_img_point(xi, yi, *self.current_image.size)

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
        return point_to_segment_distance_px(px, py, x1, y1, x2, y2)

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
        clear_line_preview(self)

    def _update_line_preview(self, mouse_x: float, mouse_y: float) -> None:
        update_line_preview(self, mouse_x, mouse_y)

    def _refresh_zoom_landmark_overlay(self) -> None:
        refresh_zoom_landmark_overlay(self)

    # Builds the landmark selection table with visibility and status controls.

    def _build_landmark_panel(self) -> None:
        build_landmark_panel(self)

    # (4) Render base image (add to class)
    def _render_base_image(self) -> None:
        render_base_image(self)

    def _on_canvas_resize(self, event=None) -> None:
        on_canvas_resize(self, event)

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
        bind_landmark_scroll(self, bind)

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
        landmark_mousewheel(self, event)

    def _scroll_landmark_into_view(self, lm: str) -> None:
        scroll_landmark_into_view(self, lm)

    # Applies stored per-landmark settings when a landmark is selected.
    def _on_landmark_selected(self) -> None:
        on_landmark_selected(self)

    def _get_landmark_meta(self, lm: str) -> Dict[str, Union[bool, str]]:
        return get_landmark_meta(self, lm)

    def _set_landmark_flag(self, lm: str, value: bool) -> None:
        set_landmark_flag(self, lm, value)

    def _get_landmark_flag(self, lm: str) -> bool:
        return get_landmark_flag(self, lm)

    def _set_landmark_note(self, lm: str, note: str) -> None:
        set_landmark_note(self, lm, note)

    def _get_landmark_note(self, lm: str) -> str:
        return get_landmark_note(self, lm)

    def _on_flag_checkbox_toggled(self, lm: str) -> None:
        on_flag_checkbox_toggled(self, lm)

    def _on_annotated_checkbox_toggled(self, lm: str) -> None:
        on_annotated_checkbox_toggled(self, lm)

    def _set_note_editor_enabled(self, enabled: bool) -> None:
        set_note_editor_enabled(self, enabled)

    def _load_note_for_selected_landmark(self) -> None:
        load_note_for_selected_landmark(self)

    def _save_note_for_selected_landmark(self) -> None:
        save_note_for_selected_landmark(self)

    def _on_note_text_modified(self, _event=None) -> None:
        on_note_text_modified(self, _event)

    def _bind_shortcut(self, sequence: str, callback) -> None:
        bind_shortcut(self, sequence, callback)

    def _note_text_shortcuts_blocked(self) -> bool:
        return note_text_shortcuts_blocked(self)

    def _sync_auto_tools_for_selected_landmark(self) -> None:
        sync_auto_tools(self)

    def _change_selected_landmark(self, step: int) -> None:
        change_selected_landmark(self, step)

    def _on_arrow_up(self, event) -> str:
        return on_arrow_up(self, event)

    def _on_arrow_down(self, event) -> str:
        return on_arrow_down(self, event)

    # Toggles visibility for all landmarks and redraws markers.
    def _set_all_visibility(self, value: bool) -> None:
        set_all_visibility(self, value)

    def load_landmarks_from_csv(self, path: Optional[Union[Path, str]] = None) -> None:
        load_landmarks_from_csv_io(self, path)

    def _init_database(self) -> None:
        try:
            init_database(cast(Path, self.db_path))
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Failed to initialize database:\n{e}\n\nAnnotations will not be saved.",
            )

    def _db_is_populated(self) -> bool:
        return db_is_populated(cast(Path, self.db_path))

    def _import_csv_to_db(self) -> None:
        import_csv_to_db(self)

    # Prompts to save pending changes before destructive operations.
    def _maybe_save_before_destructive_action(self, why: str = "continue") -> bool:
        return maybe_save_before_destructive_action(self, why)

    # Handles window close, offering to save unsaved annotations.
    def _on_close(self) -> None:
        session_on_close(self)

    # Opens an image, prepares canvas, and loads saved points.
    def load_image(self) -> None:
        session_load_image(self)

    def _get_image_index_from_directory(self) -> Tuple[int, list]:
        if self.absolute_current_image_path is None:
            return 0, []
        return get_image_index_from_directory(
            self.absolute_current_image_path, set(self.possible_image_suffix)
        )

    def _next_image(self) -> None:
        session_next_image(self)

    def _prev_image(self) -> None:
        session_prev_image(self)

    def _on_pg_down(self, event) -> None:
        on_pg_down(self)

    def _on_pg_up(self, event) -> None:
        on_pg_up(self)

    def _on_backspace(self, event) -> None:
        on_backspace(self)

    def _on_1_press(self, event) -> None:
        on_1_press(self)

    def _on_2_press(self, event) -> None:
        on_2_press(self)

    def _on_3_press(self, event) -> None:
        on_3_press(self)

    def _on_4_press(self, event) -> None:
        on_4_press(self)

    def change_image_quality(self, val: int) -> None:
        change_image_quality_io(self, val)

    def _update_path_var(self) -> None:
        update_path_var(self)

    def load_image_from_path(self, path) -> None:
        session_load_image_from_path(self, path)

    def _prepare_landmark_data(self, for_json=None):
        return prepare_landmark_data(self, for_json)

    def _canonical_image_state_for_path(self, image_path: Path) -> str:
        return canonical_image_state_for_path(self, image_path)

    def _current_image_state_string(self) -> str:
        return current_image_state_string(self)

    def _refresh_saved_snapshot_for_current_image(self) -> None:
        refresh_saved_snapshot(self)

    def _current_image_has_unsaved_changes(self) -> bool:
        return current_image_has_unsaved_changes(self)

    def _maybe_autosave_current_image(self) -> bool:
        return maybe_autosave_current_image(self)

    def _auto_save_to_db(self) -> bool:
        return auto_save_to_db(self)

    # Writes annotations (and LOB/ROB settings) back to the CSV.
    def save_annotations(self) -> bool:
        return save_annotations_flow(self)

    def _init_onedrive_credentials(self) -> None:
        init_onedrive_credentials(self)

    def _schedule_onedrive_backup(self, delay_ms: int = 5000) -> None:
        schedule_onedrive_backup(self, delay_ms)

    def _fire_onedrive_backup(self) -> None:
        fire_onedrive_backup(self)

    def _backup_to_onedrive(self, *paths: Path) -> None:
        backup_to_onedrive(self, *paths)

    def _backup_with_progress_dialog(self, files: list) -> None:
        backup_with_progress_dialog(self, files)

    def _export_db_to_csv(self) -> None:
        export_db_to_csv(self)

    def _get_annotations(self) -> Tuple[Dict[str, AnnotationValue], int]:
        return get_annotations(self)

    def load_points(self, show_message: bool = True) -> None:
        load_points_io(self, show_message)

    # Updates the disabled “Annotated” checkboxes based on available points.
    def _update_found_checks(self, pts_dict):
        update_found_checks(self, pts_dict)

    def _draw_points(self) -> None:
        draw_points(self)

    # Removes any connector lines between paired landmarks.
    def _remove_pair_lines(self):
        remove_pair_lines(self)

    # Finds a landmark by lowercase name, returning the exact key.
    def _find_landmark_key(self, name_lower: str):
        return find_landmark_key(self, name_lower)

    def _update_pair_lines(self) -> None:
        update_pair_lines(self)

    def _toggle_extended_crosshair(self) -> None:
        toggle_extended_crosshair(self)

    def _on_extended_crosshair_length_change(self, _value: str) -> None:
        on_extended_crosshair_length_change(self, _value)

    def _update_extended_crosshair(self, x: float, y: float) -> None:
        update_extended_crosshair(self, x, y)

    def _hide_extended_crosshair(self) -> None:
        hide_extended_crosshair(self)

    def _toggle_hover(self) -> None:
        toggle_hover(self)

    def _on_radius_change(self, _value: str) -> None:
        on_radius_change(self, _value)

    # Moves the hover circle with the mouse within image bounds.
    def _on_mouse_move(self, event) -> None:
        on_mouse_move(self, event)

    def _on_canvas_leave(self, event) -> None:
        on_canvas_leave(self, event)

    # Adjusts hover radius via standard mouse wheel events.
    def _on_mousewheel(self, event) -> None:
        on_mousewheel(self, event)

    # Adjusts hover radius for Linux button-4/5 events.
    def _on_scroll_linux(self, direction: int) -> None:
        on_scroll_linux(self, direction)

    # Changes the hover radius and triggers a redraw if it changed.
    def _change_radius(self, delta: int) -> None:
        change_radius(self, delta)

    def _update_hover_circle(self, x, y) -> None:
        update_hover_circle(self, x, y)

    def _update_mouse_crosshair(self, x: float, y: float) -> None:
        update_mouse_crosshair(self, x, y)

    def _hide_mouse_crosshair(self) -> None:
        hide_mouse_crosshair(self)

    def _on_right_button_press(self, event) -> None:
        on_right_button_press(self, event)

    def _on_right_button_release(self, event) -> None:
        on_right_button_release(self, event)

    def _hide_hover_circle(self) -> None:
        hide_hover_circle(self)

    def _remove_all_overlays(self):
        remove_all_overlays(self)

    def _remove_overlay_for(self, lm: str) -> None:
        remove_overlay_for(self, lm)

    def _update_overlay_for(self, lm: str) -> None:
        update_overlay_for(self, lm)

    def _render_overlay_for(
        self,
        lm: str,
        mask,
        fill_rgba=(0, 255, 255, 120),
    ) -> None:
        render_overlay_for(self, lm, mask, fill_rgba)

    # Handles click to place a landmark and optionally run LOB/ROB segmentation.
    def _on_left_press(self, event) -> None:
        on_left_press(self, event)

    def _check_left_right_order_for_landmark(
        self,
        lm: str,
        new_x: float,
        new_y: float,
    ) -> bool:
        return check_left_right_order_for_landmark(self, lm, new_x, new_y)

    def _on_left_drag(self, event) -> None:
        on_left_drag(self, event)

    def _on_left_release(self, event) -> None:
        on_left_release(self, event)

    def _delete_current_landmark(self) -> None:
        delete_current_landmark(self)

    # Triggers re-segmentation if the selected landmark is LOB/ROB.
    def _resegment_selected_if_needed(self) -> None:
        resegment_selected_if_needed(self)

    # Runs the chosen segmentation method for a landmark and updates overlay.
    def _resegment_for(self, lm: str, apply_saved_settings: bool = False) -> None:
        resegment_for(self, lm, apply_saved_settings)

    def _segment_with_fallback(self, x: int, y: int, lm: str) -> np.ndarray | None:
        return None

    # Converts image to preprocessed grayscale (CLAHE + blur).
    def _preprocess_gray(self):
        return preprocess_gray(np.array(self.current_image), self.use_clahe.get())

    # Segments a region via flood fill with optional edge-lock barrier.
    def _segment_ff(self, x: int, y: int) -> np.ndarray | None:
        return segment_ff(
            np.array(self.current_image),
            x,
            y,
            int(self.fill_sensitivity.get()),
            self.edge_lock.get(),
            int(self.edge_lock_width.get()),
            self.use_clahe.get(),
        )

    # Segments a region via adaptive thresholding and connected components.
    def _segment_adaptive_cc(self, x: int, y: int) -> np.ndarray | None:
        return segment_adaptive_cc(
            np.array(self.current_image),
            x,
            y,
            int(self.fill_sensitivity.get()),
            self.use_clahe.get(),
        )

    # Rejects implausible masks and performs a closing for cleanup.
    def _sanity_and_clean(self, mask: np.ndarray) -> np.ndarray | None:
        return sanity_and_clean(mask)

    # Dilates (positive) or erodes (negative) a mask by the requested steps.
    def _grow_shrink(self, mask: np.ndarray, steps: int) -> np.ndarray:
        return grow_shrink(mask, steps)

    # Returns a dict of the current UI segmentation settings.
    def _current_settings_dict(self) -> Dict:
        return current_settings_dict(self)

    # Stores current UI settings for a specific landmark on this image.
    def _store_current_settings_for(self, lm: str) -> None:
        store_current_settings_for(self, lm)

    # Applies saved settings for a landmark back into the UI controls.
    def _apply_settings_to_ui_for(self, lm: str) -> None:
        apply_settings_to_ui_for(self, lm)

    # Toggle visibility.
    def _set_selected_visibility(self, visible: bool) -> None:
        set_selected_visibility(self, visible)

    def _on_arrow_left(self, event) -> None:
        on_arrow_left(self)

    def _on_arrow_right(self, event) -> None:
        on_arrow_right(self)

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
        on_h_press(self)

    def _open_landmark_reference(self, event=None) -> None:
        open_landmark_reference(self)

    def _on_landmark_ref_dialog_closed(self) -> None:
        on_landmark_ref_dialog_closed(self)

    def _configure_linux_fonts(self) -> None:
        configure_linux_fonts(self)

    def _refresh_image_listbox(self) -> None:
        session_refresh_image_listbox(self)

    def _on_image_list_select(self, _event=None) -> None:
        session_on_image_list_select(self, _event)

    def _count_allowed_landmarks_for_current_image(self, image_path: Path) -> int:
        return session_count_allowed_landmarks(self, image_path)

    def _count_completed_landmarks_for_current_image(self, image_path: Path) -> int:
        return session_count_completed_landmarks(self, image_path)

    def _image_progress_text(self, image_path: Path) -> str:
        return session_image_progress_text(self, image_path)

    def _image_progress_done(self, image_path: Path) -> bool:
        return session_image_progress_done(self, image_path)

    def _widget_y_in_inner(self, widget) -> int:
        return widget_y_in_inner(self, widget)

    def _get_csv_images_from_directory(self, dir: Path) -> list[Path]:
        return session_get_csv_images_from_directory(self, dir)

    def _find_unannotated_images(self) -> None:
        session_find_unannotated_images(self)

    def _update_queue_status(self) -> None:
        session_update_queue_status(self)

    def _exit_queue_mode(self) -> None:
        session_exit_queue_mode(self)

    def _change_method_to_ff(self) -> None:
        change_method_to_ff(self)

    def _change_method_to_acc(self) -> None:
        change_method_to_acc(self)

    def _check_csv_images(self) -> None:
        session_check_csv_images(self)

    def _exit_csv_check_mode(self) -> None:
        session_exit_csv_check_mode(self)

if __name__ == "__main__":
    # Feature 1 change
    # Feature 2 change
    # Testing Tags
    app = AnnotationGUI()
    app.option_add("*Label.font", "helvetica 20 bold")
    app.mainloop()
