"""UI construction — all widget creation extracted from AnnotationGUI._setup_ui."""

from __future__ import annotations

# pyright: reportPrivateUsage=false, reportUnusedCallResult=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING, cast

from dataset_config import load_datasets_config  # pyright: ignore[reportImplicitRelativeImport]

if TYPE_CHECKING:
    from main import AnnotationGUI  # pyright: ignore[reportImplicitRelativeImport]


def build_ui(gui: AnnotationGUI) -> None:
    """Master UI builder — replaces _setup_ui body."""
    PANEL_WIDTH = 450
    SCROLLBAR_WIDTH = 18
    IMAGE_LIST_HEIGHT = 180
    CANVAS_HEIGHT = 220

    gui.option_add("*Scale.takeFocus", "0")
    gui.option_add("*Checkbutton.takeFocus", "0")
    gui.option_add("*Button.takeFocus", "0")
    gui.option_add("*Entry.takeFocus", "0")
    gui.option_add("*TCombobox.takeFocus", "0")

    main = tk.Frame(gui)
    main.pack(fill="both", expand=True)

    left_tools = tk.Frame(main, width=PANEL_WIDTH)
    left_tools.pack(side=tk.LEFT, fill="y", padx=(10, 5), pady=10)
    left_tools.pack_propagate(False)
    gui._left_tools = left_tools

    gui.canvas = tk.Canvas(main, bg="grey", highlightthickness=0)
    gui.canvas.pack(side=tk.LEFT, fill="both", expand=True)

    ctrl = tk.Frame(main, width=PANEL_WIDTH)
    ctrl.pack(side=tk.RIGHT, fill="y", padx=(5, 10), pady=10)
    ctrl.pack_propagate(False)
    gui._ctrl = ctrl

    _build_left_tools(gui, left_tools)
    _build_center_canvas(gui)
    _build_right_controls(
        gui,
        ctrl,
        PANEL_WIDTH,
        SCROLLBAR_WIDTH,
        IMAGE_LIST_HEIGHT,
        CANVAS_HEIGHT,
    )


def _build_left_tools(gui: AnnotationGUI, left_tools: tk.Frame) -> None:
    """Build zoom view, hover circle, femoral axis, crosshair tools."""
    zoom_wrap = ttk.LabelFrame(left_tools, text="Zoom View")
    zoom_wrap.pack(fill="x", pady=(0, 8))
    gui.zoom_canvas = tk.Canvas(
        zoom_wrap,
        width=450,
        height=450,
        bg="black",
        highlightthickness=0,
    )
    gui.zoom_canvas.pack(fill="x", padx=0, pady=0)
    tk.Scale(
        zoom_wrap,
        from_=2,
        to=40,
        orient="horizontal",
        label="Zoom (x)",
        variable=gui.zoom_percent,
        command=gui._on_zoom_change,
        font=gui.dialogue_font,
    ).pack(fill="x", padx=6, pady=(6, 6))
    tk.Checkbutton(
        zoom_wrap,
        text="Show Selected Landmark",
        variable=gui.show_selected_landmark_in_zoom,
        command=gui._refresh_zoom_landmark_overlay,
        font=gui.dialogue_font,
    ).pack(anchor="w", padx=6, pady=(0, 6))
    gui.after(0, gui._render_black_zoom_view)

    hover_wrap = ttk.LabelFrame(left_tools, text="Hover Circle Tool")
    hover_wrap.pack(fill="x")
    tk.Checkbutton(
        hover_wrap,
        text="Show Hover Circle",
        variable=gui.hover_enabled,
        command=gui._toggle_hover,
        font=gui.dialogue_font,
    ).pack(anchor="w", padx=6, pady=(6, 0))
    gui.radius_scale = tk.Scale(
        hover_wrap,
        from_=1,
        to=300,
        orient="horizontal",
        label="Hover Radius",
        variable=gui.hover_radius,
        command=gui._on_radius_change,
        font=gui.dialogue_font,
    )
    gui.radius_scale.config(state="disabled")
    gui.radius_scale.pack(fill="x", padx=6, pady=6)

    axis_wrap = ttk.LabelFrame(left_tools, text="Femoral Axis Tool")
    axis_wrap.pack(fill="x", pady=(8, 0))

    tk.Checkbutton(
        axis_wrap,
        text="Show Femoral Axis",
        variable=gui.femoral_axis_enabled,
        command=gui._toggle_femoral_axis,
        font=gui.dialogue_font,
    ).pack(anchor="w", padx=6, pady=(6, 0))

    gui.femoral_axis_count_scale = tk.Scale(
        axis_wrap,
        from_=1,
        to=20,
        orient="horizontal",
        label="N Orthogonal Projections",
        variable=gui.femoral_axis_count,
        command=gui._on_femoral_axis_count_change,
        font=gui.dialogue_font,
    )
    gui.femoral_axis_count_scale.config(state="disabled")
    gui.femoral_axis_count_scale.pack(fill="x", padx=6, pady=(6, 2))

    gui.femoral_axis_whisker_tip_length_scale = tk.Scale(
        axis_wrap,
        from_=1,
        to=80,
        orient="horizontal",
        label="Whisker Tip Length",
        variable=gui.femoral_axis_whisker_tip_length,
        command=gui._on_femoral_axis_whisker_tip_length_change,
        font=gui.dialogue_font,
    )
    gui.femoral_axis_whisker_tip_length_scale.config(state="disabled")
    gui.femoral_axis_whisker_tip_length_scale.pack(fill="x", padx=6, pady=(0, 6))

    cross_wrap = ttk.LabelFrame(left_tools, text="Extended Crosshair Tool")
    cross_wrap.pack(fill="x", pady=(8, 0))

    tk.Checkbutton(
        cross_wrap,
        text="Show Extended Crosshair",
        variable=gui.extended_crosshair_enabled,
        command=gui._toggle_extended_crosshair,
        font=gui.dialogue_font,
    ).pack(anchor="w", padx=6, pady=(6, 0))

    gui.crosshair_length_scale = tk.Scale(
        cross_wrap,
        from_=5,
        to=400,
        orient="horizontal",
        label="Crosshair Length",
        variable=gui.extended_crosshair_length,
        command=gui._on_extended_crosshair_length_change,
        font=gui.dialogue_font,
    )
    gui.crosshair_length_scale.config(state="disabled")
    gui.crosshair_length_scale.pack(fill="x", padx=6, pady=6)

    tk.Label(
        left_tools,
        text=(
            f"App: v{gui._get_app_version()}\n"
            f"Protocol: v{gui._get_protocol_version()}\n"
            "NOT FDA APPROVED"
        ),
        font=gui.dialogue_font,
        fg="grey50",
        anchor="w",
        justify="left",
    ).pack(side="bottom", fill="x", padx=6, pady=(0, 4))


def _build_center_canvas(gui: AnnotationGUI) -> None:
    """Bind canvas events and set drawing fonts."""
    gui.canvas.bind("<Configure>", gui._on_canvas_resize)
    gui.canvas.bind("<ButtonPress-1>", gui._on_left_press)
    gui.canvas.bind("<B1-Motion>", gui._on_left_drag)
    gui.canvas.bind("<ButtonRelease-1>", gui._on_left_release)
    gui.canvas.bind("<Motion>", gui._on_mouse_move)
    gui.canvas.bind("<Leave>", gui._on_canvas_leave)
    gui.canvas.bind("<ButtonPress-3>", gui._on_right_button_press)
    gui.canvas.bind("<ButtonRelease-3>", gui._on_right_button_release)
    gui.canvas.bind("<MouseWheel>", gui._on_mousewheel)
    gui.canvas.bind("<Button-4>", lambda e: gui._on_scroll_linux(1))
    gui.canvas.bind("<Button-5>", lambda e: gui._on_scroll_linux(-1))

    gui.landmark_font = tkfont.Font(family="Liberation Sans", size=18, weight="bold")
    gui.shadow_font = tkfont.Font(family="Liberation Sans", size=20, weight="bold")


def _build_right_controls(
    gui: AnnotationGUI,
    ctrl: tk.Frame,
    PANEL_WIDTH: int,
    SCROLLBAR_WIDTH: int,
    IMAGE_LIST_HEIGHT: int,
    CANVAS_HEIGHT: int,
) -> None:
    """Build all right-panel controls."""
    _build_study_data_section(gui, ctrl)
    _build_action_buttons(gui, ctrl)
    _build_image_metadata(gui, ctrl)
    _build_image_list(gui, ctrl, PANEL_WIDTH, IMAGE_LIST_HEIGHT)
    _build_landmark_section(gui, ctrl, PANEL_WIDTH, SCROLLBAR_WIDTH, CANVAS_HEIGHT)
    _build_note_editor(gui, ctrl)


def _build_study_data_section(gui: AnnotationGUI, ctrl: tk.Frame) -> None:
    """Build study-data download controls."""
    dl_frame = ttk.LabelFrame(ctrl, text="Study Data")
    dl_frame.pack(fill="x", pady=(0, 8))

    gui._datasets_config = load_datasets_config()
    ds_names = [ds.name for ds in gui._datasets_config.datasets]

    gui._selected_ds_name = tk.StringVar()
    if ds_names:
        gui._selected_ds_name.set(ds_names[0])

    gui._ds_dropdown = ttk.Combobox(
        dl_frame,
        textvariable=gui._selected_ds_name,
        values=ds_names,
        state="readonly",
        font=gui.dialogue_font,
    )
    gui._ds_dropdown.pack(fill="x", padx=6, pady=(4, 2))
    gui._ds_dropdown.bind(
        "<<ComboboxSelected>>",
        lambda _e: gui._dl_status_var.set(gui._initial_dl_status()),
    )

    gui._dl_status_var = tk.StringVar(value=gui._initial_dl_status())
    tk.Label(
        dl_frame,
        textvariable=gui._dl_status_var,
        font=gui.dialogue_font,
        fg="grey40",
        anchor="w",
        wraplength=420,
        justify="left",
    ).pack(fill="x", padx=6, pady=(2, 2))

    gui._dl_button = tk.Button(
        dl_frame,
        text="Download",
        command=gui._on_download_data,
        font=gui.heading_font,
        state="normal" if ds_names else "disabled",
    )
    gui._dl_button.pack(fill="x", padx=6, pady=(0, 6))


def _build_action_buttons(gui: AnnotationGUI, ctrl: tk.Frame) -> None:
    """Build top-level action buttons."""
    tk.Button(
        ctrl,
        text="Load Data",
        command=gui.load_data,
        font=gui.heading_font,
    ).pack(fill="x", pady=5)
    tk.Button(
        ctrl,
        text="Load Image",
        command=gui.load_image,
        font=gui.heading_font,
    ).pack(fill="x", pady=5)
    tk.Button(
        ctrl,
        text="Next Image",
        command=gui._next_image,
        font=gui.heading_font,
    ).pack(fill="x", pady=5)
    tk.Button(
        ctrl,
        text="Previous Image",
        command=gui._prev_image,
        font=gui.heading_font,
    ).pack(fill="x", pady=5)
    tk.Button(
        ctrl,
        text="Save Annotations",
        command=gui.save_annotations,
        font=gui.heading_font,
    ).pack(fill="x", pady=5)

    gui.autosave_check = tk.Checkbutton(
        ctrl,
        text="Autosave",
        variable=gui.autosave_var,
        font=gui.dialogue_font,
    )
    gui.autosave_check.pack(anchor="w", pady=(0, 6))


def _build_image_metadata(gui: AnnotationGUI, ctrl: tk.Frame) -> None:
    """Build image metadata controls."""
    img_frame = ttk.LabelFrame(ctrl, text="Image + Quality")
    img_frame.pack(fill="x", pady=(10, 10))

    row_meta = ttk.Frame(img_frame)
    row_meta.pack(fill="x", padx=6, pady=(0, 6))

    gui.image_flag_check = tk.Checkbutton(
        row_meta,
        text="Image Flag",
        variable=gui.image_flag_var,
        command=gui._on_image_flag_widget_changed,
        font=gui.dialogue_font,
        fg="black",
        activeforeground="black",
        disabledforeground="black",
        selectcolor=cast(str, gui.cget("bg")),
    )
    gui.image_flag_check.pack(side="left", padx=(0, 12))

    tk.Label(row_meta, text="Dir:", font=gui.dialogue_font).pack(
        side="left", padx=(0, 2)
    )
    gui.direction_dropdown = ttk.Combobox(
        row_meta,
        textvariable=gui.image_direction_var,
        values=["AP", "PA"],
        state="readonly",
        font=gui.dialogue_font,
        width=4,
        takefocus=False,
    )
    gui.direction_dropdown.pack(side="left")
    gui.direction_dropdown.bind("<<ComboboxSelected>>", gui._on_image_direction_changed)

    row_meta2 = ttk.Frame(img_frame)
    row_meta2.pack(fill="x", padx=6, pady=(0, 6))

    tk.Label(row_meta2, text="View:", font=gui.dialogue_font).pack(side="left")
    gui.view_dropdown = ttk.Combobox(
        row_meta2,
        textvariable=gui.current_view_var,
        state="readonly",
        font=gui.dialogue_font,
        width=24,
        takefocus=False,
    )
    gui.view_dropdown.pack(side="left", fill="x", expand=True)
    gui.view_dropdown.bind("<<ComboboxSelected>>", gui._on_view_selected)


def _build_image_list(
    gui: AnnotationGUI,
    ctrl: tk.Frame,
    PANEL_WIDTH: int,
    IMAGE_LIST_HEIGHT: int,
) -> None:
    """Build image list treeview."""
    tk.Label(ctrl, text="Images in JSON:", font=gui.heading_font).pack(anchor="w")

    image_container = tk.Frame(
        ctrl,
        bd=1,
        relief="sunken",
        width=PANEL_WIDTH,
        height=IMAGE_LIST_HEIGHT,
    )
    image_container.pack(fill="x", pady=(2, 8))
    image_container.pack_propagate(False)

    gui.image_tree = ttk.Treeview(
        image_container,
        columns=("image", "progress"),
        show="headings",
        height=8,
    )
    gui.image_tree.heading("image", text="Image")
    gui.image_tree.heading("progress", text="Done")
    gui.image_tree.column("image", width=290, anchor="w")
    gui.image_tree.column("progress", width=90, anchor="center")
    gui.image_tree.pack(side=tk.LEFT, fill="both", expand=True)

    image_scrollbar = tk.Scrollbar(
        image_container,
        orient="vertical",
        command=gui.image_tree.yview,
    )
    image_scrollbar.pack(side=tk.RIGHT, fill="y")
    gui.image_tree.configure(yscrollcommand=image_scrollbar.set)

    gui.image_tree.bind("<<TreeviewSelect>>", gui._on_image_list_select)
    gui.image_tree.bind("<Enter>", lambda _e: gui._bind_image_list_scroll(True))
    gui.image_tree.bind("<Leave>", lambda _e: gui._bind_image_list_scroll(False))


def _build_landmark_section(
    gui: AnnotationGUI,
    ctrl: tk.Frame,
    PANEL_WIDTH: int,
    SCROLLBAR_WIDTH: int,
    CANVAS_HEIGHT: int,
) -> None:
    """Build landmark panel and visibility controls."""
    lm_heading_row = tk.Frame(ctrl)
    lm_heading_row.pack(fill="x")
    tk.Label(lm_heading_row, text="Landmarks:", font=gui.heading_font).pack(side="left")
    if gui._landmark_ref is not None:
        tk.Button(
            lm_heading_row,
            text="?",
            command=gui._open_landmark_reference,
            font=gui.dialogue_font,
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
    tk.Label(lp_header, text="View", anchor="w", font=gui.heading_font).grid(
        row=0,
        column=0,
        sticky="w",
        padx=(2, 4),
    )
    tk.Label(lp_header, text="Name", anchor="w", font=gui.heading_font).grid(
        row=0,
        column=1,
        sticky="w",
        padx=(2, 4),
    )
    tk.Label(lp_header, text="Ann.", anchor="w", font=gui.heading_font).grid(
        row=0,
        column=2,
        sticky="w",
        padx=(2, 4),
    )
    tk.Label(lp_header, text="Flag", anchor="w", font=gui.heading_font).grid(
        row=0,
        column=3,
        sticky="w",
        padx=(2, 4),
    )

    gui.landmark_panel_container = tk.Frame(
        ctrl,
        bd=1,
        relief="sunken",
        width=PANEL_WIDTH,
        height=CANVAS_HEIGHT,
    )
    gui.landmark_panel_container.pack(fill="x", pady=(0, 0))
    gui.landmark_panel_container.pack_propagate(False)

    gui.lp_canvas = tk.Canvas(
        gui.landmark_panel_container,
        height=CANVAS_HEIGHT,
        width=PANEL_WIDTH - SCROLLBAR_WIDTH,
        highlightthickness=0,
    )
    gui.lp_canvas.pack(side=tk.LEFT, fill="both")
    gui.lp_scrollbar = tk.Scrollbar(
        gui.landmark_panel_container,
        orient="vertical",
        command=gui.lp_canvas.yview,
    )
    gui.lp_scrollbar.pack(side=tk.RIGHT, fill="y")
    gui.lp_canvas.configure(yscrollcommand=gui.lp_scrollbar.set)
    gui.lp_inner = tk.Frame(gui.lp_canvas)
    gui.lp_canvas.create_window((0, 0), window=gui.lp_inner, anchor="nw")
    gui.lp_inner.bind(
        "<Configure>",
        lambda e: gui.lp_canvas.configure(scrollregion=gui.lp_canvas.bbox("all")),
    )
    gui.lp_inner.bind("<Enter>", lambda e: gui._bind_landmark_scroll(True))
    gui.lp_inner.bind("<Leave>", lambda e: gui._bind_landmark_scroll(False))

    ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=(6, 6))
    buttons_row = tk.Frame(ctrl)
    buttons_row.pack(fill="x", pady=(0, 6))
    tk.Button(
        buttons_row,
        text="View All",
        command=lambda: gui._set_all_visibility(True),
        font=gui.dialogue_font,
    ).pack(side="left", expand=True, fill="x", padx=(0, 4))
    tk.Button(
        buttons_row,
        text="View None",
        command=lambda: gui._set_all_visibility(False),
        font=gui.dialogue_font,
    ).pack(side="left", expand=True, fill="x")


def _build_note_editor(gui: AnnotationGUI, ctrl: tk.Frame) -> None:
    """Build landmark note editor."""
    note_wrap = ttk.LabelFrame(ctrl, text="Landmark Note")
    note_wrap.pack(fill="x", pady=(8, 0))

    gui.note_text = tk.Text(
        note_wrap,
        height=8,
        wrap="word",
        font=gui.dialogue_font,
    )
    gui.note_text.pack(fill="x", padx=6, pady=6)
    gui.note_text.bind("<<Modified>>", gui._on_note_text_modified)
    gui._set_note_editor_enabled(False)
