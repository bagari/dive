import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog

_PAD = {"padx": 10, "pady": 2}

def choose_paths(title: str) -> list[str]:
    """Open a multi-file picker; return chosen paths or [] on cancel."""
    if sys.platform == "darwin":
        return _osascript_pick(title, multiple=True)
    if sys.platform == "win32":
        return _powershell_pick(title, multiple=True)
    files = filedialog.askopenfilenames(title=title)
    return list(files) if files else []

def choose_path(title: str) -> str:
    """Open a single-file picker; return chosen path or '' on cancel."""
    if sys.platform == "darwin":
        result = _osascript_pick(title, multiple=False)
        return result[0] if result else ""
    if sys.platform == "win32":
        result = _powershell_pick(title, multiple=False)
        return result[0] if result else ""
    path = filedialog.askopenfilename(title=title)
    return path if path else ""

def _osascript_pick(title: str, *, multiple: bool) -> list[str]:
    if multiple:
        script = (
            f'set fs to (choose file with prompt "{title}" with multiple selections allowed)\n'
            'set out to ""\n'
            'repeat with f in fs\n'
            '    set out to out & POSIX path of f & linefeed\n'
            'end repeat\n'
            'return out'
        )
    else:
        script = (
            f'set f to (choose file with prompt "{title}")\n'
            'return POSIX path of f'
        )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line for line in result.stdout.strip().split("\n") if line]


def _powershell_pick(title: str, *, multiple: bool) -> list[str]:
    multiselect = "true" if multiple else "false"
    output_expr = "$f.FileNames -join [Environment]::NewLine" if multiple else "$f.FileName"
    script = (
        '[System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms") | Out-Null;'
        '$f = New-Object System.Windows.Forms.OpenFileDialog;'
        f'$f.Multiselect = ${multiselect};'
        f'$f.Title = "{title}";'
        f'if ($f.ShowDialog() -eq "OK") {{ {output_expr} }}'
    )
    result = subprocess.run(["powershell", "-Command", script], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line for line in result.stdout.strip().split("\n") if line]


# Dialog
class AddItemsDialog:
    """ Modal Tk dialog that collects DiVE CLI arguments and prints them on submit. """
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("DiVE — Diffusion Visualization and Explorer | LoBeS")
        self.window.geometry("600x600")
        self.window.resizable(False, True)
        self._init_state()
        self._build_ui()

    def _init_state(self):
        # Selected paths
        self.masks: list[str] = []
        self.tracts: list[str] = []
        self.meshes: list[str] = []
        self.stats_csvs: list[str] = []
        self.transform: str = ""
        self.warp: str = ""
        self.warp_ref: str = ""
        self.inverse = tk.IntVar()
        self.warp_source_var = tk.StringVar(value="dsi_studio")
        self.warp_first_var = tk.IntVar()
        self.tract_width_var = tk.IntVar(value=1)
        self.seg_method_var = tk.StringVar(value="None")
        self.num_segments = tk.IntVar(value=10)
        self.mask_color_var = tk.StringVar()
        self.tract_color_var = tk.StringVar()
        self.mesh_color_var = tk.StringVar()
        self.mask_opacity_var = tk.StringVar(value="1.0")
        self.tract_opacity_var = tk.StringVar(value="1.0")
        self.mesh_opacity_var = tk.StringVar(value="1.0")
        self.threshold_var = tk.DoubleVar(value=0.05)
        self.range_min_var = tk.StringVar()
        self.range_max_var = tk.StringVar()
        self.log_p_var = tk.IntVar()
        self.colormap_var = tk.StringVar(value="RdBu")

    ## Layout
    def _build_ui(self):
        body = self._build_scrollable_body()
        self._build_input_files_row(body)
        self._build_tract_params_section(body)
        self._build_object_style_section(body)
        self._build_statistics_section(body)
        self._build_submit_button(body)

    def _build_scrollable_body(self) -> ttk.Frame:
        canvas = tk.Canvas(self.window, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.window, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * e.delta / 120), "units"),
        )
        return body

    def _build_input_files_row(self, body: ttk.Frame):
        files_frame = ttk.Frame(body)

        # Section header
        ttk.Label(files_frame, text="Input Files:", font="Arial 11 bold").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=(14, 6), pady=(6, 4),
        )

        # Row 1 — ROI files
        ttk.Label(files_frame, text="ROIs:").grid(row=1, column=0, sticky="w", padx=(14, 6))
        ttk.Button(files_frame, text="Mask", command=self._choose_masks ).grid(row=1, column=1, padx=3)
        ttk.Button(files_frame, text="Tract", command=self._choose_tracts).grid(row=1, column=2, padx=3)
        ttk.Button(files_frame, text="Mesh", command=self._choose_meshes).grid(row=1, column=3, padx=3)

        # Row 2 — Linear transform + inverse
        ttk.Label(files_frame, text="Linear:").grid(
            row=2, column=0, sticky="w", padx=(14, 6), pady=(6, 0),
        )
        self.transform_button = ttk.Button(
            files_frame, text="Transform", command=self._choose_transform,
        )
        self.transform_button.grid(row=2, column=1, columnspan=3, sticky="ew", padx=3, pady=(6, 0))
        ttk.Checkbutton(files_frame, text="Inverse", variable=self.inverse).grid(
            row=2, column=4, sticky="w", padx=(2, 14), pady=(6, 0),
        )

        # Row 3 — Non-linear warp + ref + source + warp-first (single dense row)
        ttk.Label(files_frame, text="Non-linear:").grid(
            row=3, column=0, sticky="w", padx=(14, 6), pady=(6, 6),
        )
        self.warp_button = ttk.Button(files_frame, text="Warp", command=self._choose_warp)
        self.warp_button.grid(row=3, column=1, sticky="ew", padx=3, pady=(6, 6))
        self.warp_ref_button = ttk.Button(
            files_frame, text="Warp Ref", command=self._choose_warp_ref,
        )
        self.warp_ref_button.grid(row=3, column=2, sticky="ew", padx=3, pady=(6, 6))
        ttk.Combobox(
            files_frame, textvariable=self.warp_source_var,
            values=["dsi_studio", "ants"], state="readonly", width=11,
        ).grid(row=3, column=3, sticky="w", padx=3, pady=(6, 6))
        ttk.Checkbutton(files_frame, text="Warp first", variable=self.warp_first_var).grid(
            row=3, column=4, sticky="w", padx=(2, 14), pady=(6, 6),
        )

        files_frame.columnconfigure(1, weight=1)
        files_frame.columnconfigure(2, weight=1)
        files_frame.pack(fill="x")
        ttk.Separator(body, orient="horizontal").pack(fill="x", padx=10, pady=(0, 4))

    def _build_tract_params_section(self, body: ttk.Frame):
        self._add_section_header(body, "Tract Parameters")
        tract_frame = self._add_form_frame(body)

        # Track-width slider
        self.tract_width_display = tk.Label(
            tract_frame, text="1", fg="#1a6bbf", width=3, font="Arial 10",
        )
        ttk.Label(tract_frame, text="Track Width:").grid(row=0, column=0, sticky="w", **_PAD)
        tk.Scale(
            tract_frame, from_=1, to=15, orient="horizontal",
            variable=self.tract_width_var,
            command=lambda v: self.tract_width_display.config(text=str(int(float(v)))),
        ).grid(row=0, column=1, sticky="ew", **_PAD)
        self.tract_width_display.grid(row=0, column=2, padx=6)

        # Segmentation method
        method_combo = ttk.Combobox(
            tract_frame, textvariable=self.seg_method_var,
            values=["None", "centerline", "hyperplane", "linear", "spline"],
            state="readonly", width=14,
        )
        method_combo.bind("<<ComboboxSelected>>", self._toggle_segments_spinbox)
        self._add_labeled_row(tract_frame, "Segmentation Method:", 1, method_combo)

        # Number of segments
        self.segments_spinbox = ttk.Spinbox(
            tract_frame, from_=2, to=500, textvariable=self.num_segments, width=8,
        )
        self.segments_spinbox.state(["disabled"])
        self._add_labeled_row(
            tract_frame, "No. of Segments:", 2, self.segments_spinbox,
            hint="(disabled when None)",
        )

    def _build_object_style_section(self, body: ttk.Frame):
        self._add_section_header(body, "Object Style")
        style_frame = ttk.Frame(body)
        style_frame.pack(fill="x", padx=14, pady=2)
        style_frame.columnconfigure(1, weight=1)

        # Header row
        ttk.Label(style_frame, text="", width=6).grid(row=0, column=0, padx=(10, 4))
        ttk.Label(style_frame, text="Color (name or #hex)", font="Arial 10").grid(
            row=0, column=1, sticky="w", padx=4,
        )
        ttk.Label(style_frame, text="Opacity", font="Arial 10").grid(row=0, column=2, padx=(4, 10))

        # One row per object kind
        rows = [
            ("Mask", self.mask_color_var, self.mask_opacity_var),
            ("Tract", self.tract_color_var, self.tract_opacity_var),
            ("Mesh", self.mesh_color_var, self.mesh_opacity_var),
        ]
        for idx, (label, color_var, opacity_var) in enumerate(rows, start=1):
            ttk.Label(style_frame, text=label, font="Arial 11 bold").grid(
                row=idx, column=0, sticky="w", padx=(10, 4), pady=2,
            )
            ttk.Entry(style_frame, textvariable=color_var).grid(
                row=idx, column=1, sticky="ew", padx=4, pady=2,
            )
            ttk.Entry(style_frame, textvariable=opacity_var, width=7).grid(
                row=idx, column=2, padx=(4, 10), pady=2,
            )

    def _build_statistics_section(self, body: ttk.Frame):
        self._add_section_header(body, "Statistics")
        stats_frame = self._add_form_frame(body)

        ttk.Button(stats_frame, text="Add CSV for Mask", command=self._choose_stats_csvs).grid(
            row=0, column=0, columnspan=3, pady=4,
        )

        self._add_labeled_row(
            stats_frame, "Threshold Value:", 1,
            ttk.Entry(stats_frame, textvariable=self.threshold_var),
        )

        # Min / max range pair
        ttk.Label(stats_frame, text="Value Range:").grid(row=2, column=0, sticky="w", **_PAD)
        range_frame = ttk.Frame(stats_frame)
        ttk.Label(range_frame, text="Min").pack(side="left")
        ttk.Entry(range_frame, textvariable=self.range_min_var, width=9).pack(side="left", padx=2)
        ttk.Label(range_frame, text="Max").pack(side="left", padx=(6, 0))
        ttk.Entry(range_frame, textvariable=self.range_max_var, width=9).pack(side="left", padx=2)
        range_frame.grid(row=2, column=1, sticky="w", **_PAD)

        # Log-scale
        self.log_p_display = tk.Label(
            stats_frame, text="Default: Don't apply", fg="#1a6bbf", font="Arial 10",
        )
        ttk.Checkbutton(
            stats_frame, text="Log Scale", variable=self.log_p_var,
            command=self._toggle_log_label,
        ).grid(row=3, column=0, sticky="w", **_PAD)
        self.log_p_display.grid(row=3, column=1, sticky="w", **_PAD)

        self._add_labeled_row(
            stats_frame, "Color Map:", 4,
            ttk.Entry(stats_frame, textvariable=self.colormap_var),
        )

    def _build_submit_button(self, body: ttk.Frame):
        ttk.Separator(body, orient="horizontal").pack(fill="x", padx=10, pady=6)
        ttk.Button(body, text="Submit", command=self._submit).pack(pady=8)

    ## Layout helpers
    @staticmethod
    def _add_section_header(parent: ttk.Frame, title: str):
        ttk.Label(parent, text=title, font="Arial 13 bold").pack(
            anchor="center", padx=10, pady=(8, 2),
        )
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=(0, 4))

    @staticmethod
    def _add_form_frame(parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=14, pady=1)
        frame.columnconfigure(1, weight=1)
        return frame

    @staticmethod
    def _add_labeled_row(parent: ttk.Frame, text: str, row: int, widget, *, colspan=1, hint=None):
        """Place a label + widget pair on one grid row, with optional hint to the right."""
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", **_PAD)
        widget.grid(row=row, column=1, columnspan=colspan, sticky="ew", **_PAD)
        if hint:
            tk.Label(parent, text=hint, fg="#1a6bbf", font="Arial 10").grid(
                row=row, column=2, padx=6,
            )

    ## File-picker callbacks
    def _choose_masks(self):
        self.masks = choose_paths("Select NIfTI Files")

    def _choose_tracts(self):
        self.tracts = choose_paths("Select Tract Files")

    def _choose_meshes(self):
        self.meshes = choose_paths("Select Mesh Files")

    def _choose_stats_csvs(self):
        self.stats_csvs = choose_paths("Select CSV for Mask")

    def _choose_transform(self):
        path = choose_path("Select Transform Matrix")
        if path:
            self.transform = path
            self.transform_button.config(text=f"Transform: {os.path.basename(path)[:24]}")

    def _choose_warp(self):
        path = choose_path("Select Warp Field NIfTI")
        if path:
            self.warp = path
            self.warp_button.config(text=f"Warp: {os.path.basename(path)[:24]}")

    def _choose_warp_ref(self):
        path = choose_path("Select Warp Reference NIfTI")
        if path:
            self.warp_ref = path
            self.warp_ref_button.config(text=f"Warp Ref: {os.path.basename(path)[:20]}")

    ## State-toggle callbacks
    def _toggle_segments_spinbox(self, _event=None):
        if self.seg_method_var.get() == "None":
            self.segments_spinbox.state(["disabled"])
        else:
            self.segments_spinbox.state(["!disabled"])

    def _toggle_log_label(self):
        self.log_p_display.config(
            text="Applied" if self.log_p_var.get() else "Default: Don't apply",
        )

    ## Submit
    def _submit(self):
        """Print the assembled command string on stdout and close.

        The parent process reads stdout and feeds it to ``Show._parse_command``.
        """
        args: list[str] = []
        if self.masks: args.append("--mask " + " ".join(self.masks))
        if self.tracts: args.append("--tract " + " ".join(self.tracts))
        if self.meshes: args.append("--mesh " + " ".join(self.meshes))
        if self.stats_csvs: args.append("--stats_csv " + " ".join(self.stats_csvs))
        if self.transform: args.append(f"--transform {self.transform}")
        if self.inverse.get():
            args.append("--inverse")
        if self.warp:
            args.append(f"--warp {self.warp}")
            args.append(f"--warp_source {self.warp_source_var.get()}")
        if self.warp_ref:
            args.append(f"--warp_ref {self.warp_ref}")
        if self.warp_first_var.get():
            args.append("--warp_first")

        ## Tract parameters
        width = self.tract_width_var.get()
        if width != 1:
            args.append(f"--tract_width {width}")

        if self.seg_method_var.get() != "None":
            args.append(f"--seg_method {self.seg_method_var.get()}")
            args.append(f"--num_segments {self.num_segments.get()}")

        ## Object style: colors
        if self.mask_color_var.get():
            args.append(f"--mask_colors {self.mask_color_var.get()}")
        if self.tract_color_var.get():
            args.append(f"--tract_colors {self.tract_color_var.get()}")
        if self.mesh_color_var.get():
            args.append(f"--mesh_colors {self.mesh_color_var.get()}")

        ## Object style: opacities
        mask_op = self.mask_opacity_var.get().strip()
        if mask_op and float(mask_op) != 1.0:
            args.append(f"--mask_opacity {mask_op}")
        tract_op = self.tract_opacity_var.get().strip()
        if tract_op and float(tract_op) != 1.0:
            args.append(f"--tract_opacity {tract_op}")
        mesh_op = self.mesh_opacity_var.get().strip()
        if mesh_op and float(mesh_op) != 1.0:
            args.append(f"--mesh_opacity {mesh_op}")

        ## Statistics
        if self.threshold_var.get() != 0.05:
            args.append(f"--threshold {self.threshold_var.get()}")
        range_min = self.range_min_var.get().strip()
        range_max = self.range_max_var.get().strip()
        if range_min and range_max:
            args.append(f"--value_range {range_min} {range_max}")
        if self.log_p_var.get():
            args.append("--log_p_value")
        if self.colormap_var.get() != "RdBu":
            args.append(f"--map {self.colormap_var.get()}")

        ## stdout is parsed by the parent process:
        print(" ".join(args))
        self.window.destroy()

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    AddItemsDialog().run()
