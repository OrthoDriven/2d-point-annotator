#!/usr/bin/env python3
"""Correct legacy hover circle radii in annotation JSON files.

Usage: pixi run python scripts/circle_corrector.py path/to/data.json
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any, Optional

import cv2  # type: ignore[import-untyped]
from PIL import Image, ImageTk

HOVER_CIRCLE_LANDMARKS = {"L-FHC", "R-FHC", "L-AC", "R-AC"}
VIEWPORT_SIZE = 800
CIRCLE_COLOR = "orange"
CIRCLE_WIDTH = 2


class CircleCorrector(tk.Tk):
    def __init__(self, json_path: Path) -> None:
        super().__init__()
        self.title(f"Circle Corrector — {json_path.name}")
        self.geometry(f"{VIEWPORT_SIZE + 200}x{VIEWPORT_SIZE + 100}")

        self._json_path = json_path
        self._json_dir = json_path.parent
        self._data: dict[str, Any] = {}
        self._images: list[dict[str, Any]] = []
        self._current_idx = 0
        self._photo: Optional[ImageTk.PhotoImage] = None

        print(f"[init] JSON path: {self._json_path}")
        print(f"[init] JSON dir:  {self._json_dir}")

        self._load_json()
        self._build_ui()
        self._show_current_image()

    def _load_json(self) -> None:
        print("[load] Reading JSON...")
        with self._json_path.open() as f:
            self._data = json.load(f)
        self._images = self._data.get("images", [])
        print(f"[load] Total images in JSON: {len(self._images)}")

        for i, rec in enumerate(self._images[:3]):
            ip = rec.get("image_path", "MISSING")
            print(f"[load]   images[{i}].image_path = {ip!r}")

    def _resolve_image_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path.resolve()
        standard = (self._json_dir / path).resolve()
        if standard.exists():
            return standard
        parts = path.parts
        if len(parts) > 1 and parts[0] == self._json_dir.name:
            fallback = (self._json_dir / Path(*parts[1:])).resolve()
            print(f"[resolve] Stripped leading dir: {path} -> {fallback}")
            return fallback
        return standard

    def _build_ui(self) -> None:
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self._canvas = tk.Canvas(
            canvas_frame, width=VIEWPORT_SIZE, height=VIEWPORT_SIZE, bg="black"
        )
        h_scroll = tk.Scrollbar(
            canvas_frame, orient="horizontal", command=self._canvas.xview
        )
        v_scroll = tk.Scrollbar(
            canvas_frame, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self._canvas.pack(side="left", fill="both", expand=True)

        panel = tk.Frame(self, width=180)
        panel.pack(side="right", fill="y", padx=(0, 8), pady=8)
        panel.pack_propagate(False)

        tk.Label(panel, text="Scale Factor", font=("", 12, "bold")).pack(pady=(8, 4))

        self._scale_var = tk.DoubleVar(value=1.0)
        self._slider = tk.Scale(
            panel,
            from_=0.1,
            to=5.0,
            resolution=0.01,
            orient="vertical",
            variable=self._scale_var,
            length=400,
            command=self._on_scale_change,
        )
        self._slider.pack(pady=8)
        self._bind_scroll(self._slider, self._on_scroll_scale)

        self._scale_label = tk.Label(panel, text="1.00", font=("", 14))
        self._scale_label.pack()

        tk.Button(panel, text="Reset", command=self._reset_scale).pack(pady=8)

        tk.Frame(panel, height=1, bg="grey").pack(fill="x", pady=8, padx=8)

        nav = tk.Frame(panel)
        nav.pack(pady=4)
        tk.Button(nav, text="← Prev", command=self._prev_image).pack(
            side="left", padx=4
        )
        tk.Button(nav, text="Next →", command=self._next_image).pack(
            side="left", padx=4
        )

        self._image_label = tk.Label(panel, text="", font=("", 10))
        self._image_label.pack(pady=4)

        self._landmarks_label = tk.Label(panel, text="", font=("", 9), justify="left")
        self._landmarks_label.pack(pady=4)

        tk.Frame(panel, height=1, bg="grey").pack(fill="x", pady=8, padx=8)

        tk.Button(
            panel,
            text="Save",
            command=self._save,
            font=("", 12, "bold"),
            width=12,
        ).pack(pady=4)
        tk.Button(panel, text="Quit", command=self.destroy, width=12).pack(pady=4)

        self.bind("<Left>", lambda e: self._prev_image())
        self.bind("<Right>", lambda e: self._next_image())
        self.bind("<Control-s>", lambda e: self._save())

    def _bind_scroll(self, widget: tk.Widget, callback: Any) -> None:
        widget.bind("<MouseWheel>", callback)
        widget.bind("<Button-4>", callback)
        widget.bind("<Button-5>", callback)

    def _on_scroll_scale(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        delta = 0
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        elif hasattr(event, "delta") and event.delta:
            delta = 1 if event.delta > 0 else -1

        if delta == 0:
            return

        step = 0.01
        new_val = self._scale_var.get() + delta * step
        new_val = round(max(0.1, min(5.0, new_val)), 2)
        self._scale_var.set(new_val)
        self._scale_label.config(text=f"{new_val:.3f}")
        self._show_current_image()

    def _circle_images(self) -> list[dict[str, Any]]:
        result = []
        for rec in self._images:
            ann = rec.get("annotations", {}) or {}
            for lm in HOVER_CIRCLE_LANDMARKS:
                raw = ann.get(lm)
                if isinstance(raw, dict) and "radius" in raw and "value" in raw:
                    result.append(rec)
                    break
        return result

    def _show_current_image(self) -> None:
        circle_images = self._circle_images()
        print(f"[show] Images with circle landmarks: {len(circle_images)}")

        if not circle_images:
            self._canvas.delete("all")
            self._canvas.create_text(
                VIEWPORT_SIZE / 2,
                VIEWPORT_SIZE / 2,
                text="No hover circle landmarks found\nin this JSON file.",
                fill="white",
                font=("", 14),
            )
            self._image_label.config(text="No images")
            self._landmarks_label.config(text="")
            return

        if self._current_idx >= len(circle_images):
            self._current_idx = len(circle_images) - 1
        if self._current_idx < 0:
            self._current_idx = 0

        rec = circle_images[self._current_idx]
        self._image_label.config(
            text=f"Image {self._current_idx + 1} / {len(circle_images)}"
        )

        img_path_str = rec.get("image_path", "")
        print(f"[show] image_path from JSON: {img_path_str!r}")

        img_path = self._resolve_image_path(img_path_str)
        print(f"[show] Resolved path: {img_path}")
        print(f"[show] Exists: {img_path.exists()}")

        if not img_path.exists():
            self._canvas.delete("all")
            self._canvas.create_text(
                VIEWPORT_SIZE / 2,
                VIEWPORT_SIZE / 2,
                text=f"Image not found:\n{img_path}",
                fill="red",
                font=("", 12),
            )
            self._landmarks_label.config(text="")
            return

        print(f"[show] Calling cv2.imread...")
        img = cv2.imread(str(img_path))
        print(
            f"[show] cv2.imread returned: {'array' + str(img.shape) if img is not None else 'None'}"
        )

        if img is None:
            self._canvas.delete("all")
            self._canvas.create_text(
                VIEWPORT_SIZE / 2,
                VIEWPORT_SIZE / 2,
                text=f"Failed to load:\n{img_path}",
                fill="red",
                font=("", 12),
            )
            self._landmarks_label.config(text="")
            return

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]
        print(f"[show] Image size: {w}x{h}")

        self._disp_scale = 1.0
        print(f"[show] disp_scale=1.0 (1:1 pixel display)")

        pil_img = Image.fromarray(img_rgb)
        self._photo = ImageTk.PhotoImage(pil_img)

        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._canvas.configure(scrollregion=(0, 0, w, h))

        ann = rec.get("annotations", {}) or {}
        scale = self._scale_var.get()
        circle_info = []

        for lm in HOVER_CIRCLE_LANDMARKS:
            raw = ann.get(lm)
            if not isinstance(raw, dict):
                continue

            val = raw.get("value")
            radius = raw.get("radius")
            if val is None or radius is None:
                continue

            if isinstance(val, list) and len(val) == 2:
                img_x, img_y = float(val[0]), float(val[1])
            else:
                continue

            screen_r = radius * scale

            print(f"[show]   {lm}: img=({img_x:.1f},{img_y:.1f}) r={screen_r:.1f}")

            self._canvas.create_oval(
                img_x - screen_r,
                img_y - screen_r,
                img_x + screen_r,
                img_y + screen_r,
                outline=CIRCLE_COLOR,
                width=CIRCLE_WIDTH,
            )
            self._canvas.create_text(
                img_x,
                img_y - screen_r - 10,
                text=lm,
                fill=CIRCLE_COLOR,
                font=("", 9),
            )

            circle_info.append(f"{lm}: {radius:.0f} → {radius * scale:.1f}")

        self._landmarks_label.config(
            text="\n".join(circle_info) if circle_info else "No circles"
        )
        print(f"[show] Done. Circles drawn: {len(circle_info)}")

    def _on_scale_change(self, _value: str) -> None:
        self._scale_label.config(text=f"{self._scale_var.get():.2f}")
        self._show_current_image()

    def _reset_scale(self) -> None:
        self._scale_var.set(1.0)
        self._scale_label.config(text="1.00")
        self._show_current_image()

    def _prev_image(self) -> None:
        if self._current_idx > 0:
            self._current_idx -= 1
            self._show_current_image()

    def _next_image(self) -> None:
        if self._current_idx < len(self._circle_images()) - 1:
            self._current_idx += 1
            self._show_current_image()

    def _save(self) -> None:
        scale = self._scale_var.get()

        if not messagebox.askyesno(
            "Confirm Save",
            f"Apply scale factor {scale:.2f} to all circle radii\n"
            f"and save to {self._json_path.name}?",
        ):
            return

        for rec in self._images:
            ann = rec.get("annotations", {}) or {}
            for lm in HOVER_CIRCLE_LANDMARKS:
                raw = ann.get(lm)
                if isinstance(raw, dict) and "radius" in raw:
                    raw["radius"] = round(raw["radius"] * scale, 2)

        with self._json_path.open("w") as f:
            json.dump(self._data, f, indent=2)

        messagebox.showinfo("Saved", f"Updated radii saved to {self._json_path.name}")

    def run(self) -> None:
        self.mainloop()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: pixi run python scripts/circle_corrector.py path/to/data.json")
        sys.exit(1)

    json_path = Path(sys.argv[1]).expanduser().resolve()
    print(f"[main] Resolved JSON path: {json_path}")

    if not json_path.exists():
        print(f"[main] File not found: {json_path}")
        sys.exit(1)

    print(f"[main] File exists. Launching app...")
    app = CircleCorrector(json_path)
    app.run()


if __name__ == "__main__":
    main()
