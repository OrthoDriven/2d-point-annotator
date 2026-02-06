from __future__ import annotations

import ast
import datetime
import json
import logging
import os
import platform
import shutil
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

from auth import OneDriveBackup
from dirs import APP_DIR, AUTH_DIR, BASE_DIR, BASE_DIR_PATH, PLATFORM
from path_utils import (
    extract_filename,
    filenames_match,
    normalize_path_string,
    normalize_relative_path,
)


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
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.csv_path_column = "image_path"
        self.dirty = False
        self.path_var = tk.StringVar(value="No image loaded")
        self.quality_var = tk.StringVar(value="N/A")
        self.selected_landmark = tk.StringVar(value="")
        self.landmark_visibility: Dict[str, tk.BooleanVar] = {}
        self.landmark_found = {}
        self.annotations: Dict[str, Dict[str, Tuple[float, float]]] = {}
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
        self.lm_settings: Dict[str, Dict[str, Dict]] = {}
        self.csv_loaded = False
        # Also adjust these if you want everything to match:
        # Already configured above to match heading_font
        self._setup_ui()
        self.after(0, self._lock_initial_minsize)
        self.landmarks = []
        self.unbind("<Up>")
        self.unbind("<Down>")
        self.bind("<Up>", self._on_arrow_up)
        self.bind("<Down>", self._on_arrow_down)
        self.bind("<f>", self._on_arrow_down)
        self.bind("<d>", self._on_arrow_up)
        self.bind("<Left>", self._on_arrow_left)
        self.bind("<Right>", self._on_arrow_right)
        self.bind("<Control-b>", self._on_pg_up)
        self.bind("<Control-n>", self._on_pg_down)
        self.bind("<n>", self._on_pg_down)
        self.bind("<g>", self._on_pg_down)
        self.bind("<b>", self._on_pg_up)
        self.bind("<BackSpace>", self._on_backspace)
        self.bind("<space>", self._on_space)
        self.bind("1", self._on_1_press)
        self.bind("2", self._on_2_press)
        self.bind("3", self._on_3_press)
        self.bind("4", self._on_4_press)
        self.bind("<h>", self._on_h_press)
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

    def _setup_ui(self) -> None:
        self.canvas = tk.Canvas(self, bg="grey", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill="both", expand=True)
        # recompute transform & redraw on canvas size changes
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", lambda e: self._hide_hover_circle())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_scroll_linux(1))
        self.canvas.bind("<Button-5>", lambda e: self._on_scroll_linux(-1))

        self.landmark_font = tkfont.Font(
            family="Liberation Sans", size=18, weight="bold"
        )
        self.shadow_font = tkfont.Font(family="Liberation Sans", size=20, weight="bold")

        ctrl = tk.Frame(self)
        ctrl.pack(side=tk.RIGHT, fill="y", padx=10, pady=10)
        self._ctrl = ctrl
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
        tk.Button(
            ctrl,
            text="Load CSV",
            command=self.load_landmarks_from_csv,
            font=self.heading_font,
        ).pack(fill="x", pady=5)
        img_frame = ttk.LabelFrame(ctrl, text="Image + Quality")
        img_frame.pack(fill="x", pady=(10, 10))

        row = ttk.Frame(img_frame)
        row.pack(fill="x", padx=6, pady=6)

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

        tk.Label(ctrl, text="Landmarks:", font=self.heading_font).pack(anchor="w")
        PANEL_WIDTH = 300
        SCROLLBAR_WIDTH = 18
        CANVAS_HEIGHT = 220
        self.landmark_panel_container = tk.Frame(
            ctrl, bd=1, relief="sunken", width=PANEL_WIDTH, height=CANVAS_HEIGHT
        )
        self.landmark_panel_container.pack(fill="x", pady=(2, 0))
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
        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=(6, 6))
        hover_wrap = ttk.LabelFrame(ctrl, text="Hover Circle Tool")
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
        tk.Scale(
            seg_wrap,
            from_=-10,
            to=30,
            orient="horizontal",
            label="Grow / Shrink (post)",
            variable=self.grow_shrink,
            command=lambda _v: self._apply_grow_shrink_only_for(
                self.selected_landmark.get()
            ),
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

    # Builds the landmark selection table with visibility and status controls.

    def _build_landmark_panel(self) -> None:
        for w in self.lp_inner.winfo_children():
            w.destroy()
        self.landmark_visibility.clear()
        self.landmark_found.clear()
        self.landmark_radio_widgets = {}
        self.landmark_table = tk.Frame(self.lp_inner)
        self.landmark_table.pack(fill="x", padx=2, pady=2)
        self.landmark_table.grid_columnconfigure(0, minsize=70)
        self.landmark_table.grid_columnconfigure(1, minsize=140)
        self.landmark_table.grid_columnconfigure(2, minsize=100)
        tk.Label(
            self.landmark_table, text="View", anchor="w", font=self.heading_font
        ).grid(row=0, column=0, sticky="w", padx=(2, 4), pady=(0, 2))
        tk.Label(
            self.landmark_table, text="Name", anchor="w", font=self.heading_font
        ).grid(row=0, column=1, sticky="w", padx=(2, 4), pady=(0, 2))
        tk.Label(
            self.landmark_table, text="Annotated", anchor="w", font=self.heading_font
        ).grid(row=0, column=2, sticky="w", padx=(2, 4), pady=(0, 2))
        for i, lm in enumerate(getattr(self, "landmarks", []), start=1):
            vis_var = tk.BooleanVar(value=True)
            found_var = tk.BooleanVar(value=False)
            self.landmark_visibility[lm] = vis_var
            self.landmark_found[lm] = found_var
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
            tk.Checkbutton(
                self.landmark_table,
                text="",
                variable=found_var,
                state="disabled",
                font=self.dialogue_font,
            ).grid(row=i, column=2, sticky="w", padx=(2, 4), pady=1)
        if getattr(self, "landmarks", None) and not self.selected_landmark.get():
            self.selected_landmark.set(self.landmarks[0])

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

    # (5) Handle canvas resize (add to class)
    def _on_canvas_resize(self, _event=None) -> None:
        if not self.current_image:
            return
        self._render_base_image()
        self._draw_points()
        for lm in ("LOB", "ROB"):
            self._update_overlay_for(lm)

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
        self._draw_points()
        self.after_idle(self._scroll_landmark_into_view, lm)

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
            self._maybe_save_before_destructive_action("load point name CSV")
            self.abs_csv_path = filedialog.askopenfilename(
                initialdir=BASE_DIR, filetypes=[("CSV File", ("*.csv"))]
            )
        else:
            self.abs_csv_path = str(path)

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
    def _maybe_save_before_destructive_action(self, why: str = "continue") -> None:
        if not self.current_image_path or not self.dirty:
            return
        if messagebox.askyesno(
            "Unsaved annotations",
            "You have unsaved annotation changes for this image.\n"
            f"Do you want to save before you {why}?",
        ):
            self.save_annotations()
        else:
            self.dirty = False

    # Handles window close, offering to save unsaved annotations.
    def _on_close(self) -> None:
        self._maybe_save_before_destructive_action("exit")
        self.window_close_flag = True
        if self.db_path is not None:
            self._export_db_to_csv()
        self.destroy()

    # Opens an image, prepares canvas, and loads saved points.
    def load_image(self) -> None:
        self._maybe_save_before_destructive_action("load another image")
        abs_path = filedialog.askopenfilename(
            initialdir=BASE_DIR,
            filetypes=[("Image files", ("*.png", "*.jpg", "*.jpeg", "*.bmp", ".tif"))],
        )
        self.absolute_current_image_path = Path(abs_path)
        if not abs_path:
            return

        self.load_image_from_path(Path(abs_path))
        if self.landmarks:
            self.selected_landmark.set(self.landmarks[0])

        return

    def _get_image_index_from_directory(self) -> Tuple[int, list]:
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
            if len(all_files) == idx + 1:
                messagebox.showwarning(
                    "End of Directory",
                    "You've reached the end of the current image directory, please use"
                    "'Load Image' to find a new image, or use 'Prev Image' to move backward",
                )
            else:
                self.absolute_current_image_path = Path(
                    self.absolute_current_image_path.resolve().parent
                    / all_files[idx + 1]
                )
                self.load_image_from_path(Path(self.absolute_current_image_path))

    def _prev_image(self) -> None:
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
            if idx == 0:
                messagebox.showwarning(
                    "Beginning of Directory",
                    "You've reached the beginning of the current image directory, please use 'Load Image' to find a new image, or use 'Next Image' to move forward",
                )
            else:
                self.absolute_current_image_path = Path(
                    self.absolute_current_image_path.resolve().parent
                    / all_files[idx - 1]
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
            self.current_image.convert("RGB")

        except Exception as e:
            messagebox.showerror("Load Image", f"Failed to open image:\n{e}")
            return

        # rel_path = os.path.relpath(path, BASE_DIR)
        rel_path = PurePath(path.resolve()).relative_to(
            BASE_DIR.resolve(), walk_up=True
        )
        self.current_image_path = Path(rel_path)
        image_filename = PurePath(rel_path).name
        w, h = self.current_image.size
        self.canvas.config(width=w, height=h)
        self.canvas.delete("all")
        self.base_img_item = None
        self._remove_all_overlays()
        self.last_seed.clear()
        self.lm_settings.setdefault(str(self.current_image_path), {})
        self.annotations.setdefault(str(self.current_image_path), {})
        self.load_points(show_message=False)
        self._render_base_image()
        self._hide_hover_circle()
        self.dirty = False
        self._update_path_var()

        if self.landmarks:
            self.selected_landmark.set(self.landmarks[0])

        self._draw_points()

    def _prepare_landmark_data(self) -> dict:
        """Prepare landmark data dict for database storage."""
        pts, quality = self._get_annotations()
        per_img_settings = self.lm_settings.get(str(self.current_image_path), {})

        landmark_data = {}
        for lm in self.landmarks:
            if lm in pts:
                x, y = pts[lm]
                if lm in ("LOB", "ROB"):
                    st = per_img_settings.get(lm, self._current_settings_dict())
                    method_code = "FF" if st["method"] == "Flood Fill" else "ACC"
                    landmark_data[lm] = [
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
                    landmark_data[lm] = [float(x), float(y)]

        return landmark_data

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
    def save_annotations(self) -> None:
        """Save to database, then export to CSV."""
        if not self.current_image_path:
            messagebox.showwarning("Save", "No image loaded.")
            return

        # Get annotation data
        pts, quality = self._get_annotations()
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
            return
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Unexpected error while saving:\n{e}",
            )
            return

        # Export to CSV (periodic, not every save)
        self._export_db_to_csv()

        self.dirty = False
        if PLATFORM != "Linux":
            messagebox.showinfo("Saved", "Annotations saved")

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

    def _backup_to_onedrive(self, csv_path: Path) -> None:
        """
        Backup database and CSV to OneDrive.

        Uploads to: pelvic-2d-points-backup/<username>/<YYYY-MM-DD>/

        On window close, shows progress dialog while uploading.
        Otherwise uses async upload to avoid blocking GUI.
        """
        if self.db_path is None:
            return

        files_to_backup = [self.db_path, csv_path]

        if self.window_close_flag:
            # Show progress dialog and upload in background
            self._backup_with_progress_dialog(files_to_backup)
        else:
            # Async upload during normal operation - don't block GUI
            self.onedrive_backup.backup_multiple(
                files_to_backup,
                callback=lambda success, total: logger.info(
                    f"OneDrive backup: {success}/{total} files uploaded"
                ),
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

    def _get_annotations(self) -> Tuple[Dict[str, Tuple[float, float]], int]:
        """Returns (points_dict, quality) for current image."""
        if self.current_image_path is not None:
            current_filename = PurePath(self.current_image_path).name
            # Try exact match first
            key = str(self.current_image_path)
            if key in self.annotations:
                quality = self.current_image_quality  # Already loaded
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
                    sx, sy = pts[lm]
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
        for lm in self.landmarks:
            var = self.landmark_found.get(lm)
            if var is not None:
                var.set(lm in pts_dict)

    # Draws landmark markers/labels and syncs overlays and pair lines.
    def _draw_points(self) -> None:
        self.canvas.delete("marker")
        if not self.current_image_path:
            return
        # pts = self.annotations.get(self.current_image_path, {})
        pts, quality = self._get_annotations()
        self._update_found_checks(pts)
        current_image_verified = self._is_current_image_verified()
        x_curr, y_curr = self._img_to_screen(0, 0)
        label_font = self.landmark_font.copy()
        label_font.configure(size=30)

        landmark_is_labeled = self.selected_landmark.get() in pts.keys()

        self.canvas.create_text(
            x_curr,
            y_curr,
            text=self.selected_landmark.get(),
            fill=("#FFCC66" if landmark_is_labeled else "#FF8066"),
            font=label_font,
            tags="marker",
            anchor="nw",
        )

        for lm, (x, y) in pts.items():
            drawing_current_selected = lm == self.selected_landmark.get()
            y_offset_label = 16 if drawing_current_selected else 12
            oval_color = (
                "blue"
                if drawing_current_selected
                else ("red" if not current_image_verified else "green")
            )
            text_color = "orange" if drawing_current_selected else "yellow"
            font = (
                self.landmark_font if drawing_current_selected else self.dialogue_font
            )
            shadow_font = font.copy()
            shadow_font.configure(size=font.cget("size") + 1)
            vis_var = self.landmark_visibility.get(lm)
            if vis_var is not None and not vis_var.get():
                continue
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
                    x1, y1 = pts[ka]
                    x2, y2 = pts[kb]
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

    # Enables/disables the hover circle UI and hides it when disabled.
    def _toggle_hover(self) -> None:
        enabled = self.hover_enabled.get()
        self.radius_scale.config(state="normal" if enabled else "disabled")
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
        if not self.hover_enabled.get() or not self.current_image:
            return
        x0, y0, x1, y1 = self._display_rect()
        if x0 <= event.x < x1 and y0 <= event.y < y1:
            self._update_hover_circle(
                event.x, event.y
            )  # hover circle stays screen-space
        else:
            self._hide_hover_circle()

    # Adjusts hover radius via standard mouse wheel events.
    def _on_mousewheel(self, event) -> None:
        if not self.hover_enabled.get():
            return
        step = 2 if event.delta > 0 else -2
        self._change_radius(step)

    # Adjusts hover radius for Linux button-4/5 events.
    def _on_scroll_linux(self, direction: int) -> None:
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
    def _on_click(self, event) -> None:
        x0, y0, x1, y1 = self._display_rect()
        if not self.current_image:
            return
        w, h = self.current_image.size
        if not (x0 <= event.x < x1 and y0 <= event.y < y1):
            return
        xi, yi = self._screen_to_img(event.x, event.y)
        x, y = round(xi, 1), round(yi, 1)  # or clamp if you want
        lm = self.selected_landmark.get()
        if not lm:
            messagebox.showwarning(
                "No Landmark", "Please select a landmark in the list."
            )
            return
        self.annotations.setdefault(str(self.current_image_path), {})[lm] = (x, y)
        if lm in self.landmark_found:
            self.landmark_found[lm].set(True)
        self._draw_points()
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

        # Check if that annotation exists already
        if lm in self.annotations[str(self.current_image_path)].keys():
            # Delete it if it does
            del self.annotations[str(self.current_image_path)][lm]

        self._draw_points()
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

        # if apply_saved_settings:
        #     self._apply_settings_to_ui_for(lm)
        # if self.method.get() == "Flood Fill":
        #     mask = self._segment_ff(x, y)
        # else:
        #     mask = self._segment_adaptive_cc(x, y)
        if mask is None:
            messagebox.showwarning(
                "Segmentation",
                "No region found. Try toggling CLAHE, increasing Sensitivity, or switch Method.",
            )
            return
        mask = self._grow_shrink(mask, self.grow_shrink.get())
        self.seg_masks.setdefault(str(self.current_image_path), {})[lm] = mask
        self._update_overlay_for(lm)

    def _segment_with_fallback(self, x: int, y: int, lm: str) -> np.ndarray | None:
        """
        Try segmentation with multiple fallback strategies.
        Returns mask or None if all strategies fail.
        """
        # Strategy 1: Try with current settings
        if self.method.get() == "Flood Fill":
            mask = self._segment_ff(x, y)
        else:
            mask = self._segment_adaptive_cc(x, y)

        if mask is not None:
            return mask

        # Strategy 2: Try nearby seed points (jittering)
        offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 2), (-2, -2)]
        for dx, dy in offsets[1:]:  # Skip (0,0) since we already tried it
            new_x, new_y = x + dx, y + dy
            if self.method.get() == "Flood Fill":
                mask = self._segment_ff(new_x, new_y)
            else:
                mask = self._segment_adaptive_cc(new_x, new_y)

            if mask is not None:
                return mask

        # Strategy 3: Try opposite method
        if self.method.get() == "Flood Fill":
            mask = self._segment_adaptive_cc(x, y)
        else:
            mask = self._segment_ff(x, y)

        if mask is not None:
            return mask

        # Strategy 4: Try with relaxed sensitivity (more permissive)
        original_sens = self.fill_sensitivity.get()
        relaxed_sens = min(50, original_sens + 10)
        self.fill_sensitivity.set(relaxed_sens)

        if self.method.get() == "Flood Fill":
            mask = self._segment_ff(x, y)
        else:
            mask = self._segment_adaptive_cc(x, y)

        # Restore original
        self.fill_sensitivity.set(original_sens)

        if mask is not None:
            return mask

        # All strategies failed
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
        if self.abs_csv_path is None:
            return

        if self.abs_csv_path.strip() == "":
            return

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
    app = AnnotationGUI()
    app.option_add("*Label.font", "helvetica 20 bold")
    app.mainloop()
