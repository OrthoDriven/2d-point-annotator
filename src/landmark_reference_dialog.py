"""Landmark reference popup dialog — shows placement instructions for landmarks."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Any

from landmark_reference import LandmarkReference  # pyright: ignore[reportImplicitRelativeImport]

_HIGHLIGHT_BG = "#e6f0ff"
_CARD_PAD_X = 10
_CARD_PAD_Y = 6
_WINDOW_WIDTH = 450
_MAX_HEIGHT = 600


class LandmarkReferenceDialog(tk.Toplevel):
    """Popup showing landmark placement instructions.

    Two modes controlled by a checkbox:
    - Unchecked (default): shows the currently selected landmark's definition.
    - Checked: scrollable list of all landmarks, current one highlighted.
    """

    def __init__(
        self,
        parent: tk.Tk,
        reference: LandmarkReference,
        current_landmark: str | None = None,
        on_close: Any = None,
    ) -> None:
        super().__init__(parent)
        self.title("Landmark Reference")
        self.transient(parent)
        self.geometry(f"{_WINDOW_WIDTH}x400")
        self.minsize(_WINDOW_WIDTH, 200)

        self._reference = reference
        self._current_landmark = current_landmark
        self._on_close_cb = on_close
        self._card_frames: dict[str, tk.Frame] = {}

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        heading_font = tkfont.nametofont("TkDefaultFont").copy()
        heading_font.configure(weight="bold")
        self._heading_font = heading_font

        # --- Top row: checkbox left, protocol version right ---
        top_row = tk.Frame(self)
        top_row.pack(fill="x", padx=8, pady=(8, 4))

        self._show_all_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            top_row,
            text="Show all landmarks",
            variable=self._show_all_var,
            command=self._rebuild,
        ).pack(side="left")

        tk.Label(
            top_row,
            text=f"Protocol v{reference.version}",
            fg="grey50",
        ).pack(side="right")

        # --- Scrollable content area ---
        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._canvas = tk.Canvas(container, highlightthickness=0)
        self._scrollbar = tk.Scrollbar(
            container, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw"
        )

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._inner.bind("<Enter>", lambda _: self._bind_scroll(True))
        self._inner.bind("<Leave>", lambda _: self._bind_scroll(False))

        self._rebuild()

    # --- Public API ---

    def update_landmark(self, landmark_name: str | None) -> None:
        """Update which landmark is shown (called from main on selection change)."""
        self._current_landmark = landmark_name
        if self._show_all_var.get():
            self._update_highlight()
            self._scroll_to_current()
        else:
            self._rebuild()

    # --- Internal ---

    def _rebuild(self) -> None:
        """Rebuild the content area."""
        for w in self._inner.winfo_children():
            w.destroy()
        self._card_frames.clear()

        if self._show_all_var.get():
            for defn in self._reference.get_all_definitions():
                frame = self._build_card(self._inner, defn)
                frame.pack(fill="x", pady=(0, 4))
                self._card_frames[defn["acronym"]] = frame
            self._update_highlight()
        else:
            if self._current_landmark:
                defn = self._reference.get_definition(self._current_landmark)
                if defn:
                    self._build_card(self._inner, defn).pack(fill="x")
                else:
                    tk.Label(
                        self._inner,
                        text=f"No definition found for '{self._current_landmark}'.",
                        wraplength=_WINDOW_WIDTH - 40,
                    ).pack(anchor="w", pady=_CARD_PAD_Y)
            else:
                tk.Label(
                    self._inner,
                    text="No landmark selected.",
                    wraplength=_WINDOW_WIDTH - 40,
                ).pack(anchor="w", pady=_CARD_PAD_Y)

        self._inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _build_card(self, parent: tk.Widget, defn: dict[str, Any]) -> tk.Frame:
        """Build a single landmark card frame."""
        frame = tk.Frame(
            parent, bd=1, relief="groove", padx=_CARD_PAD_X, pady=_CARD_PAD_Y
        )

        # Header: Full Name (ACRONYM)
        display_acronym = defn["acronym"]
        tk.Label(
            frame,
            text=f"{defn['name']} ({display_acronym})",
            font=self._heading_font,
            anchor="w",
            wraplength=_WINDOW_WIDTH - 60,
            justify="left",
        ).pack(anchor="w")

        # Anatomical feature
        anat = defn.get("anatomical_feature")
        if anat:
            tk.Label(
                frame, text="Anatomical Feature:", font=self._heading_font, anchor="w"
            ).pack(anchor="w", pady=(6, 0))
            tk.Label(
                frame,
                text=anat,
                anchor="w",
                wraplength=_WINDOW_WIDTH - 60,
                justify="left",
            ).pack(anchor="w")

        # Placement rules
        rules = defn.get("placement_rules", {})
        if rules:
            tk.Label(
                frame, text="Placement Rules:", font=self._heading_font, anchor="w"
            ).pack(anchor="w", pady=(6, 0))
            for key, text in rules.items():
                if len(rules) == 1 and key == "general":
                    tk.Label(
                        frame,
                        text=text,
                        anchor="w",
                        wraplength=_WINDOW_WIDTH - 60,
                        justify="left",
                    ).pack(anchor="w")
                else:
                    label = key.replace("_", " ").title()
                    rule_frame = tk.Frame(frame)
                    rule_frame.pack(anchor="w", fill="x")
                    tk.Label(
                        rule_frame,
                        text=f"{label}: ",
                        anchor="w",
                        font=tkfont.Font(slant="italic"),
                    ).pack(side="left", anchor="n")
                    tk.Label(
                        rule_frame,
                        text=text,
                        anchor="w",
                        wraplength=_WINDOW_WIDTH - 120,
                        justify="left",
                    ).pack(side="left", anchor="w", fill="x", expand=True)

        return frame

    def _update_highlight(self) -> None:
        """Highlight the current landmark's card in full-list mode."""
        current_acronym = None
        if self._current_landmark:
            defn = self._reference.get_definition(self._current_landmark)
            if defn:
                current_acronym = defn["acronym"]

        for acronym, frame in self._card_frames.items():
            bg = _HIGHLIGHT_BG if acronym == current_acronym else ""
            frame.configure(bg=bg)
            for child in frame.winfo_children():
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass
                # Handle nested frames (rule_frame children)
                if isinstance(child, tk.Frame):
                    for grandchild in child.winfo_children():
                        try:
                            grandchild.configure(bg=bg)
                        except tk.TclError:
                            pass

    def _scroll_to_current(self) -> None:
        """Scroll the current landmark's card into view in full-list mode."""
        if not self._current_landmark:
            return
        defn = self._reference.get_definition(self._current_landmark)
        if not defn:
            return
        frame = self._card_frames.get(defn["acronym"])
        if not frame:
            return

        self._inner.update_idletasks()
        bbox = self._canvas.bbox("all")
        if not bbox:
            return
        total_height = bbox[3] - bbox[1]
        if total_height <= 0:
            return
        frame_y = frame.winfo_y()
        fraction = frame_y / total_height
        self._canvas.yview_moveto(fraction)

    def _on_inner_configure(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _bind_scroll(self, bind: bool) -> None:
        widget = self._canvas
        if bind:
            widget.bind("<MouseWheel>", self._on_mousewheel)
            widget.bind("<Button-4>", self._on_mousewheel)
            widget.bind("<Button-5>", self._on_mousewheel)
        else:
            widget.unbind("<MouseWheel>")
            widget.unbind("<Button-4>")
            widget.unbind("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_close(self) -> None:
        if self._on_close_cb:
            self._on_close_cb()
        self.destroy()
