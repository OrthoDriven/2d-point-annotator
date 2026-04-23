import json
import math
import itertools
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from PIL import Image, ImageTk


def load_summary(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def discover_annotator_files(summary: dict, data_dir: Path) -> dict[str, Path]:
    result = {}
    group_mapping = summary.get("group_mapping", {})
    for group_id, info in group_mapping.items():
        annotator = info["annotator"]
        file_path = data_dir / info["file"]
        if file_path.exists():
            result[annotator] = file_path
    return result


def get_shared_images(summary: dict) -> list[str]:
    membership = summary["rounds"][0]["image_membership"]
    return sorted(img for img, groups in membership.items() if len(groups) >= 2)


def load_annotator_data(path: Path) -> dict:
    """Load an annotator's JSON file."""
    with open(path) as f:
        return json.load(f)


def get_annotations_for_image(annotator_data: dict, image_path: str) -> dict:
    """Return annotations dict for a specific image, or empty dict if not found."""
    for img in annotator_data.get("images", []):
        if img["image_path"] == image_path:
            return img.get("annotations", {})
    return {}


def compute_landmark_distance(val_a, val_b) -> dict | None:
    """Compute distance metrics between two landmark values.

    Point landmarks [x,y]: returns {"type": "point", "distance": float}
    Line landmarks [[x1,y1],[x2,y2]]: returns {"type": "line", "signed_dists": [float, float], "angle_deg": float}
    Returns None if either value is None.
    """
    if val_a is None or val_b is None:
        return None

    a_is_line = isinstance(val_a[0], list)
    b_is_line = isinstance(val_b[0], list)

    if not a_is_line and not b_is_line:
        return {"type": "point", "distance": math.dist(val_a, val_b)}

    if a_is_line and b_is_line:
        return _compare_lines(val_a, val_b)

    return None


def _max_metric(pairs: dict) -> float:
    vals = []
    for r in pairs.values():
        if r["type"] == "point":
            vals.append(r["distance"])
        elif r["type"] == "line":
            vals.append(max(abs(d) for d in r["signed_dists"]))
    return max(vals) if vals else 0.0


def _compare_lines(line_a: list, line_b: list) -> dict:
    """Compare two line landmarks: signed perpendicular distances + angle."""
    ax1, ay1 = line_a[0]
    ax2, ay2 = line_a[1]
    bx1, by1 = line_b[0]
    bx2, by2 = line_b[1]

    # Direction vector of line B
    bdx, bdy = bx2 - bx1, by2 - by1
    blen = math.hypot(bdx, bdy)
    if blen < 1e-9:
        return {"type": "line", "signed_dists": [0.0, 0.0], "angle_deg": 0.0}

    # Unit normal of line B (perpendicular, pointing "left" relative to direction)
    nx, ny = -bdy / blen, bdx / blen

    # Signed distance from each endpoint of A to line B's infinite line
    d1 = (ax1 - bx1) * nx + (ay1 - by1) * ny
    d2 = (ax2 - bx1) * nx + (ay2 - by1) * ny

    # Angle between the two lines
    adx, ady = ax2 - ax1, ay2 - ay1
    alen = math.hypot(adx, ady)
    if alen < 1e-9:
        return {"type": "line", "signed_dists": [d1, d2], "angle_deg": 0.0}

    dot = (adx * bdx + ady * bdy) / (alen * blen)
    dot = max(-1.0, min(1.0, dot))  # clamp for float precision
    angle_rad = math.acos(dot)
    angle_deg = math.degrees(angle_rad)

    return {"type": "line", "signed_dists": [d1, d2], "angle_deg": angle_deg}


def compute_pairwise_distances(
    annotators: dict[str, dict], image_path: str, landmarks: list[str]
) -> dict[str, dict[tuple[str, str], dict | None]]:
    result = {}
    for lm in landmarks:
        values = {}
        for name, data in annotators.items():
            anns = get_annotations_for_image(data, image_path)
            if lm in anns:
                values[name] = anns[lm]["value"]

        pairs = {}
        for a, b in itertools.combinations(sorted(values.keys()), 2):
            dist = compute_landmark_distance(values[a], values[b])
            if dist is not None:
                pairs[(a, b)] = dist
        result[lm] = pairs
    return result


def detect_mismatches(
    annotators: dict[str, dict], image_path: str, landmarks: list[str]
) -> dict[str, str]:
    """Detect mismatches across annotators for each landmark.

    Returns {landmark: 'ok' | 'missing' | 'flagged'}
    Priority: missing > flagged > ok
    """
    result = {}
    for lm in landmarks:
        has_null = False
        has_flagged = False
        for name, data in annotators.items():
            anns = get_annotations_for_image(data, image_path)
            if lm not in anns:
                continue
            ann = anns[lm]
            if ann["value"] is None:
                has_null = True
            if ann.get("flag", False):
                has_flagged = True
        result[lm] = "missing" if has_null else ("flagged" if has_flagged else "ok")
    return result


COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#e67e22", "#9b59b6", "#1abc9c"]


class QcViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Inter-Annotator QC Viewer")
        self.geometry("1400x900")

        # State
        self.summary_path = None
        self.data_dir = None
        self.images_dir = None
        self.summary = None
        self.annotators: dict[str, dict] = {}
        self.annotator_paths: dict[str, Path] = {}
        self.shared_images: list[str] = []
        self.current_index = 0
        self.visible_annotators: set[str] = set()
        self.annotator_colors: dict[str, str] = {}

        self._build_toolbar()
        self._build_main_layout()

    def _build_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=5, pady=5)

        ttk.Label(toolbar, text="Summary:").grid(row=0, column=0, sticky="w")
        self.summary_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.summary_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(toolbar, text="Browse", command=self._browse_summary).grid(row=0, column=2)

        ttk.Label(toolbar, text="Data dir:").grid(row=1, column=0, sticky="w", pady=2)
        self.data_dir_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.data_dir_var, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(toolbar, text="Browse", command=self._browse_data_dir).grid(row=1, column=2)

        ttk.Label(toolbar, text="Images dir:").grid(row=2, column=0, sticky="w", pady=2)
        self.images_dir_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.images_dir_var, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(toolbar, text="Browse", command=self._browse_images_dir).grid(row=2, column=2)

        ttk.Button(toolbar, text="Load", command=self._load_data).grid(row=0, column=3, rowspan=3, padx=10)

    def _browse_summary(self):
        path = filedialog.askopenfilename(
            title="Select summary JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.summary_var.set(path)
            p = Path(path)
            self.data_dir_var.set(str(p.parent))

    def _browse_data_dir(self):
        path = filedialog.askdirectory(title="Select data directory")
        if path:
            self.data_dir_var.set(path)

    def _browse_images_dir(self):
        path = filedialog.askdirectory(title="Select images directory")
        if path:
            self.images_dir_var.set(path)

    def _load_data(self):
        summary_path = Path(self.summary_var.get())
        data_dir = Path(self.data_dir_var.get())
        images_dir = Path(self.images_dir_var.get())

        if not summary_path.exists():
            tk.messagebox.showerror("Error", f"Summary file not found: {summary_path}")
            return

        self.summary_path = summary_path
        self.data_dir = data_dir
        self.images_dir = images_dir

        self.summary = load_summary(summary_path)
        self.annotator_paths = discover_annotator_files(self.summary, data_dir)

        self.annotators = {}
        for name, path in self.annotator_paths.items():
            self.annotators[name] = load_annotator_data(path)

        self.annotator_colors = {
            name: COLORS[i % len(COLORS)] for i, name in enumerate(sorted(self.annotators.keys()))
        }
        self.visible_annotators = set(self.annotators.keys())

        self.shared_images = get_shared_images(self.summary)
        self.current_index = 0

        self._populate_annotator_toggles()
        self._render_current_image()

        self.status_var.set(
            f"Loaded {len(self.annotators)} annotators, {len(self.shared_images)} shared images"
        )

    def _build_main_layout(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.left_panel = ttk.Frame(main_frame, width=200)
        self.left_panel.pack(side="left", fill="y", padx=(0, 5))
        self.left_panel.pack_propagate(False)

        self.canvas_frame = ttk.Frame(main_frame)
        self.canvas_frame.pack(side="left", fill="both", expand=True)

        self.right_panel = ttk.Frame(main_frame, width=300)
        self.right_panel.pack(side="right", fill="y", padx=(5, 0))
        self.right_panel.pack_propagate(False)

        self.status_var = tk.StringVar(value="No data loaded")
        ttk.Label(self, textvariable=self.status_var, relief="sunken").pack(fill="x", padx=5, pady=2)

        self._build_left_panel()
        self._build_canvas()
        self._build_right_panel()

    def _build_left_panel(self):
        ttk.Label(self.left_panel, text="Annotators", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))

        self.annotator_frame = ttk.Frame(self.left_panel)
        self.annotator_frame.pack(fill="x")

        ttk.Separator(self.left_panel, orient="horizontal").pack(fill="x", pady=10)

        nav_frame = ttk.Frame(self.left_panel)
        nav_frame.pack(fill="x")
        ttk.Button(nav_frame, text="Prev", command=self._prev_image).pack(side="left", expand=True, fill="x")
        ttk.Button(nav_frame, text="Next", command=self._next_image).pack(side="left", expand=True, fill="x")

        self.image_index_var = tk.StringVar(value="Image: -/-")
        ttk.Label(self.left_panel, textvariable=self.image_index_var).pack(anchor="w", pady=5)

        self.image_name_var = tk.StringVar(value="")
        ttk.Label(self.left_panel, textvariable=self.image_name_var, wraplength=180).pack(anchor="w")

    def _populate_annotator_toggles(self):
        for widget in self.annotator_frame.winfo_children():
            widget.destroy()

        self.toggle_vars = {}
        for name in sorted(self.annotators.keys()):
            var = tk.BooleanVar(value=True)
            self.toggle_vars[name] = var
            color = self.annotator_colors.get(name, "#000000")

            frame = ttk.Frame(self.annotator_frame)
            frame.pack(fill="x", pady=1)

            cb = ttk.Checkbutton(frame, text=name, variable=var, command=self._on_toggle_change)
            cb.pack(side="left")

            swatch = tk.Canvas(frame, width=12, height=12, highlightthickness=0)
            swatch.create_oval(1, 1, 11, 11, fill=color, outline=color)
            swatch.pack(side="left", padx=5)

    def _on_toggle_change(self):
        self.visible_annotators = {name for name, var in self.toggle_vars.items() if var.get()}
        self._render_current_image()

    def _prev_image(self):
        if self.shared_images and self.current_index > 0:
            self.current_index -= 1
            self._render_current_image()

    def _next_image(self):
        if self.shared_images and self.current_index < len(self.shared_images) - 1:
            self.current_index += 1
            self._render_current_image()

    def _update_nav_display(self):
        if self.shared_images:
            self.image_index_var.set(f"Image: {self.current_index + 1}/{len(self.shared_images)}")
            self.image_name_var.set(self.shared_images[self.current_index])
        else:
            self.image_index_var.set("Image: -/-")
            self.image_name_var.set("")

    def _build_canvas(self):
        self.canvas = tk.Canvas(self.canvas_frame, bg="#2c3e50")
        self.canvas.pack(fill="both", expand=True)
        self.photo = None

    def _render_current_image(self):
        if not self.shared_images:
            self._update_nav_display()
            return

        self._update_nav_display()
        image_path = self.shared_images[self.current_index]
        full_path = self.images_dir / image_path

        if not full_path.exists():
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text=f"Image not found:\n{image_path}",
                fill="white",
                justify="center",
            )
            return

        img = Image.open(full_path)
        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 600

        scale = min(canvas_w / img.width, canvas_h / img.height, 1.0)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        self.photo = ImageTk.PhotoImage(img_resized)
        self.canvas.delete("all")
        self.canvas.create_image(
            canvas_w // 2, canvas_h // 2, image=self.photo, anchor="center"
        )

        self._draw_landmarks(image_path, scale, canvas_w // 2 - new_w // 2, canvas_h // 2 - new_h // 2)
        self._update_landmark_table(image_path)

    def _draw_landmarks(self, image_path: str, scale: float, offset_x: int, offset_y: int):
        radius = 6
        first_ann = next(iter(self.annotators.values()), None)
        if not first_ann:
            return
        all_landmarks = first_ann.get("landmarks", [])

        for name in sorted(self.visible_annotators):
            if name not in self.annotators:
                continue
            color = self.annotator_colors.get(name, "#000000")
            anns = get_annotations_for_image(self.annotators[name], image_path)

            for lm in all_landmarks:
                if lm not in anns:
                    continue
                val = anns[lm]["value"]
                if val is None:
                    continue

                if isinstance(val[0], list):
                    x1, y1 = val[0][0] * scale + offset_x, val[0][1] * scale + offset_y
                    x2, y2 = val[1][0] * scale + offset_x, val[1][1] * scale + offset_y
                    self.canvas.create_line(x1, y1, x2, y2, fill=color, width=2)
                else:
                    x, y = val[0] * scale + offset_x, val[1] * scale + offset_y
                    self.canvas.create_oval(
                        x - radius, y - radius, x + radius, y + radius,
                        fill=color, outline="white", width=1,
                    )

    def _build_right_panel(self):
        ttk.Label(self.right_panel, text="Landmarks", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))

        columns = ("landmark", "status", "max_dist")
        self.lm_tree = ttk.Treeview(self.right_panel, columns=columns, show="headings", height=30)
        self.lm_tree.heading("landmark", text="Landmark")
        self.lm_tree.heading("status", text="Status")
        self.lm_tree.heading("max_dist", text="Max Dist")
        self.lm_tree.column("landmark", width=80)
        self.lm_tree.column("status", width=80)
        self.lm_tree.column("max_dist", width=80)
        self.lm_tree.pack(fill="both", expand=True)

        self.lm_tree.tag_configure("ok", background="#d5f5e3")
        self.lm_tree.tag_configure("flagged", background="#fdebd0")
        self.lm_tree.tag_configure("missing", background="#fadbd8")

        self.detail_var = tk.StringVar(value="")
        ttk.Label(self.right_panel, textvariable=self.detail_var, wraplength=280, justify="left").pack(anchor="w", pady=5)

        self.lm_tree.bind("<<TreeviewSelect>>", self._on_landmark_select)

    def _update_landmark_table(self, image_path: str):
        for item in self.lm_tree.get_children():
            self.lm_tree.delete(item)

        first_ann = next(iter(self.annotators.values()), None)
        if not first_ann:
            return
        all_landmarks = first_ann.get("landmarks", [])

        mismatches = detect_mismatches(self.annotators, image_path, all_landmarks)
        distances = compute_pairwise_distances(self.annotators, image_path, all_landmarks)

        for lm in all_landmarks:
            status = mismatches.get(lm, "ok")
            lm_pairs = distances.get(lm, {})
            if lm_pairs:
                max_dist = _max_metric(lm_pairs)
                dist_str = f"{max_dist:.1f}"
            else:
                dist_str = "---"
            self.lm_tree.insert("", "end", values=(lm, status, dist_str), tags=(status,))

    def _on_landmark_select(self, event):
        sel = self.lm_tree.selection()
        if not sel:
            return
        lm = self.lm_tree.item(sel[0])["values"][0]
        image_path = self.shared_images[self.current_index]

        lines = [f"{lm}:"]
        for name in sorted(self.visible_annotators):
            anns = get_annotations_for_image(self.annotators[name], image_path)
            val = anns.get(lm, {}).get("value", "N/A")
            flag = anns.get(lm, {}).get("flag", False)
            marker = " [FLAGGED]" if flag else ""
            lines.append(f"  {name}: {val}{marker}")

        distances = compute_pairwise_distances(self.annotators, image_path, [lm])
        if distances.get(lm):
            lines.append("  Distances:")
            for (a, b), result in sorted(distances[lm].items()):
                if result["type"] == "point":
                    lines.append(f"    {a}-{b}: {result['distance']:.1f}px")
                elif result["type"] == "line":
                    sd = result["signed_dists"]
                    lines.append(
                        f"    {a}-{b}: signed=[{sd[0]:.1f}, {sd[1]:.1f}]px, angle={result['angle_deg']:.1f}°"
                    )

        self.detail_var.set("\n".join(lines))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inter-Annotator QC Viewer")
    parser.add_argument("--summary", default=None, help="Path to summary JSON")
    parser.add_argument("--json-dir", default=None, help="Directory containing annotator JSONs")
    parser.add_argument("--images-dir", default=None, help="Directory containing images")
    parser.add_argument("--max-images", type=int, default=5, help="Max shared images to report on (default 5)")
    args = parser.parse_args()

    if args.summary and args.json_dir:
        summary_path = Path(args.summary)
        json_dir = Path(args.json_dir)
        images_dir = Path(args.images_dir) if args.images_dir else None

        print(f"Loading summary: {summary_path}")
        summary = load_summary(summary_path)

        print(f"Discovering annotators in: {json_dir}")
        annotator_files = discover_annotator_files(summary, json_dir)
        print(f"Found {len(annotator_files)} annotators: {sorted(annotator_files.keys())}")

        annotators = {}
        for name, path in annotator_files.items():
            annotators[name] = load_annotator_data(path)
            n_images = len(annotators[name].get("images", []))
            print(f"  {name}: {n_images} images")

        shared_images = get_shared_images(summary)
        print(f"\nShared images: {len(shared_images)}")

        landmarks = next(iter(annotators.values()), {}).get("landmarks", [])
        print(f"Landmarks: {len(landmarks)}")

        print(f"\n{'='*60}")
        print(f"Inspecting first {min(args.max_images, len(shared_images))} shared images:")
        print(f"{'='*60}")

        for image_path in shared_images[:args.max_images]:
            print(f"\n--- {image_path} ---")

            if images_dir:
                full_path = images_dir / image_path
                print(f"  Image exists: {full_path.exists()}")

            mismatches = detect_mismatches(annotators, image_path, landmarks)
            distances = compute_pairwise_distances(annotators, image_path, landmarks)

            missing = [lm for lm, s in mismatches.items() if s == "missing"]
            flagged = [lm for lm, s in mismatches.items() if s == "flagged"]
            ok = [lm for lm, s in mismatches.items() if s == "ok"]

            print(f"  Status: {len(ok)} ok, {len(flagged)} flagged, {len(missing)} missing")

            if missing:
                print(f"  Missing: {', '.join(missing)}")
            if flagged:
                print(f"  Flagged: {', '.join(flagged)}")

            if distances:
                point_dists = []
                line_angles = []
                line_max_signed = []
                for pairs in distances.values():
                    for result in pairs.values():
                        if result["type"] == "point":
                            point_dists.append(result["distance"])
                        elif result["type"] == "line":
                            line_angles.append(result["angle_deg"])
                            line_max_signed.append(max(abs(d) for d in result["signed_dists"]))

                if point_dists:
                    print(f"  Point distances: min={min(point_dists):.1f}px, max={max(point_dists):.1f}px, mean={sum(point_dists)/len(point_dists):.1f}px")
                if line_angles:
                    print(f"  Line angles: min={min(line_angles):.1f}°, max={max(line_angles):.1f}°, mean={sum(line_angles)/len(line_angles):.1f}°")
                if line_max_signed:
                    print(f"  Line offsets: min={min(line_max_signed):.1f}px, max={max(line_max_signed):.1f}px, mean={sum(line_max_signed)/len(line_max_signed):.1f}px")

                worst = sorted(
                    [(lm, _max_metric(pairs)) for lm, pairs in distances.items() if pairs],
                    key=lambda x: x[1], reverse=True
                )[:3]
                if worst:
                    print(f"  Worst landmarks:")
                    for lm, d in worst:
                        print(f"    {lm}: {d:.1f}")

        print(f"\n{'='*60}")
        print("Data layer verification complete.")
    else:
        app = QcViewer()
        app.mainloop()
