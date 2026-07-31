"""
WxCleaner - 微信重复文件清理工具
Path B: CustomTkinter + Apple HIG design

Custom table component built on Canvas + Frame (CTk has no Treeview).
All original functionality preserved.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import os
import time
import subprocess
import sys
from send2trash import send2trash
from file_actions import move_to_trash
from scanner import find_duplicates
from version import __version__


# ════════════════════════════════════════════════════════════
#  Design Tokens — Apple HIG
# ════════════════════════════════════════════════════════════

class C:
    """Color palette"""
    BG          = "#FFFFFF"
    BG_SEC      = "#F5F5F7"
    BG_ROW_ALT = "#FAFAFA"
    BG_SEL      = "#E8F0FE"
    BG_HOVER    = "#F0F0F5"
    TEXT        = "#1D1D1F"
    TEXT2       = "#86868B"
    TEXT3       = "#AEAEB2"
    SEP         = "#D2D2D7"
    ACCENT      = "#007AFF"
    ACCENT_HOV  = "#0066CC"
    ACCENT_PRS  = "#0055B3"
    GREEN       = "#34C759"
    RED         = "#FF3B30"
    RED_HOV     = "#E0342B"
    RED_PRS     = "#C92D25"
    ORANGE      = "#FF9500"
    BORDER      = "#E5E5EA"


class T:
    """Typography"""
    _f = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei"
    TITLE   = (_f, 18)
    HEADING  = (_f, 13)
    BODY    = (_f, 13)
    CAPTION = (_f, 11)
    CAPTION_B = (_f, 11, "bold")
    MONO    = ("SF Mono", "Menlo", _f) if sys.platform == "darwin" else ("Consolas", _f)


class S:
    """Spacing"""
    PAD       = 24
    GAP       = 16
    COMP      = 12
    ROW_H     = 38
    BTN_H     = 36


def _decode_touchpad_delta(raw_delta):
    """Decode Tk 9's packed signed horizontal and vertical touchpad deltas."""
    raw = int(raw_delta) & 0xFFFFFFFF
    delta_y = raw & 0xFFFF
    delta_x = (raw >> 16) & 0xFFFF

    if delta_y >= 0x8000:
        delta_y -= 0x10000
    if delta_x >= 0x8000:
        delta_x -= 0x10000

    return delta_x, delta_y


# ════════════════════════════════════════════════════════════
#  Custom Table (Canvas + Frame, replaces ttk.Treeview)
# ════════════════════════════════════════════════════════════

class FileTable(ctk.CTkFrame):
    """
    A custom table widget built on CTkCanvas for scrolling
    and CTkFrame rows for content.  Supports:
      - click to select, Cmd+click multi-select, Shift+click range
      - hover highlight
      - right-click context menu
      - mouse-wheel / trackpad scroll
    """

    def __init__(self, parent, columns, widths, **kw):
        super().__init__(parent, fg_color=C.BG, corner_radius=0, border_width=0)

        self.col_keys = list(columns)
        self.col_widths = widths
        self._column_specs = [
            (
                180 if width == 0 and col == "path" else max(0, int(width)),
                1 if width == 0 else 0,
            )
            for col, width in zip(self.col_keys, self.col_widths)
        ]
        self.rows = []          # [(frame, {col: label}, values_list, tags_tuple)]
        self.selected = set()   # row indices
        self._last_idx = None

        self._on_select = kw.pop("on_select", None)
        self._on_menu = kw.pop("on_menu", None)
        self._row_bindtag = f"FileTableRow{id(self)}"

        # ── shared table viewport ──
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._header = ctk.CTkFrame(self, fg_color=C.BG_SEC, corner_radius=8, height=36)
        self._header.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=(4, 2))
        self._header.grid_propagate(False)
        self._configure_columns(self._header)
        self._header_cells = {}

        for index, col in enumerate(self.col_keys):
            anchor = "center" if col in ("num", "size", "mtime", "status") else "w"
            label = ctk.CTkLabel(
                self._header, text=self._col_label(col),
                font=T.HEADING, text_color=C.TEXT2, anchor=anchor,
            )
            label.grid(row=0, column=index, sticky="ew", padx=(8, 4))
            self._header_cells[col] = label

        self._separator = ctk.CTkFrame(self, height=1, fg_color=C.BORDER)
        self._separator.grid(row=1, column=0, sticky="ew", padx=(4, 0))

        # ─ scrollable body ──
        scroll_increment = 8 if sys.platform == "darwin" else 0
        self._canvas = tk.Canvas(
            self, bg=C.BG, highlightthickness=0, bd=0,
            yscrollincrement=scroll_increment,
        )
        # Use native tk.Scrollbar — CTkScrollbar has compatibility issues with tk.Canvas
        self._scroll = tk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview,
            bg=C.BG_SEC, troughcolor=C.BG_SEC,
            activebackground=C.SEP, elementborderwidth=0,
            width=10,
        )
        self._canvas.configure(yscrollcommand=self._scroll.set)

        self._canvas.grid(row=2, column=0, sticky="nsew", padx=(4, 0), pady=2)
        self._scroll.grid(row=2, column=1, sticky="ns", padx=(0, 2), pady=2)

        self._body = ctk.CTkFrame(self._canvas, fg_color=C.BG, corner_radius=0)
        self._win = self._canvas.create_window((0, 0), window=self._body, anchor="nw")

        # Only update scrollregion when content size changes (not on every configure)
        self._last_scrollregion = None
        self._body.bind("<Configure>", self._update_scrollregion)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        # ── Event delegation: one row bindtag shared by row frames and labels ──
        self._canvas.bind("<MouseWheel>", self._scroll_wheel)
        self._canvas.bind("<Button-4>", self._scroll_wheel_linux)
        self._canvas.bind("<Button-5>", self._scroll_wheel_linux)

        self._body.bind("<Button-1>", self._on_body_click)
        self._body.bind("<Button-2>", self._on_body_menu)
        self._body.bind("<Button-3>", self._on_body_menu)
        self._body.bind("<MouseWheel>", self._scroll_wheel)
        self._body.bind("<Button-4>", self._scroll_wheel_linux)
        self._body.bind("<Button-5>", self._scroll_wheel_linux)
        self._bind_optional_touchpad(self._canvas)
        self._bind_optional_touchpad(self._body)
        self._bind_optional_touchpad(getattr(self._body, "_canvas", None))
        self.bind_class(self._row_bindtag, "<Button-1>", self._on_body_click)
        self.bind_class(self._row_bindtag, "<Button-2>", self._on_body_menu)
        self.bind_class(self._row_bindtag, "<Button-3>", self._on_body_menu)
        self.bind_class(self._row_bindtag, "<MouseWheel>", self._scroll_wheel)
        self.bind_class(self._row_bindtag, "<Button-4>", self._scroll_wheel_linux)
        self.bind_class(self._row_bindtag, "<Button-5>", self._scroll_wheel_linux)
        self._bind_optional_touchpad_class()
        self.bind_class(self._row_bindtag, "<Enter>", self._on_body_enter)
        self.bind_class(self._row_bindtag, "<Leave>", self._on_body_leave)

    # ── public API ──

    def insert(self, values, tags=()):
        idx = len(self.rows)
        row_fg = C.BG_ROW_ALT if idx % 2 else C.BG
        rf = ctk.CTkFrame(self._body, fg_color=row_fg, corner_radius=0, height=S.ROW_H)
        rf.pack(fill="x")
        rf.grid_propagate(False)
        self._configure_columns(rf)

        # Store row index on the frame for event delegation
        rf.idx = idx
        self._attach_row_bindtag(rf)

        labels = {}
        for index, col in enumerate(self.col_keys):
            val = values.get(col, "")
            anchor = "center" if col in ("num", "size", "mtime", "status") else "w"
            color = self._tag_color(col, tags)
            lbl = ctk.CTkLabel(
                rf, text=str(val), font=T.BODY,
                text_color=color, anchor=anchor,
            )
            lbl.grid(row=0, column=index, sticky="ew", padx=(8, 4))
            self._attach_row_bindtag(lbl)
            labels[col] = lbl

        self.rows.append((rf, labels, dict(values), tags))

    def clear(self):
        for rf, _, _, _ in self.rows:
            rf.destroy()
        self.rows.clear()
        self.selected.clear()
        self._last_idx = None

    def get_children(self):
        return list(range(len(self.rows)))

    def item_values(self, idx, col=None):
        if idx < 0 or idx >= len(self.rows):
            return {} if col is None else ""
        vals = self.rows[idx][2]
        if col is None:
            return dict(vals)
        return vals.get(col, "")

    def selection_set(self, indices):
        self.selected = set(indices)
        self._repaint()

    def selection_add(self, indices):
        self.selected.update(indices)
        self._repaint()

    def selection_remove(self, indices=None):
        if indices is None:
            self.selected.clear()
        else:
            self.selected -= set(indices)
        self._repaint()

    def selection(self):
        return list(self.selected)

    def exists(self, idx):
        return 0 <= idx < len(self.rows)

    def delete(self, idx):
        if 0 <= idx < len(self.rows):
            self.rows[idx][0].destroy()
            self.rows.pop(idx)
            self.selected.discard(idx)
            # re-index selected set and row frame indices
            self.selected = {i if i < idx else i - 1 for i in self.selected if i != idx}
            for i in range(idx, len(self.rows)):
                self.rows[i][0].idx = i

    def set_tags(self, idx, tags):
        if 0 <= idx < len(self.rows):
            self.rows[idx] = (self.rows[idx][0], self.rows[idx][1], self.rows[idx][2], tags)
            # update status label color
            color = self._tag_color("status", tags)
            self.rows[idx][1].get("status", tk.NONE).configure(text_color=color)

    def set_values(self, idx, values):
        if 0 <= idx < len(self.rows):
            self.rows[idx][2].update(values)
            for col, lbl in self.rows[idx][1].items():
                if col in values:
                    lbl.configure(text=str(values[col]))

    # ── internals ──

    def _configure_columns(self, widget):
        for index, (minsize, weight) in enumerate(self._column_specs):
            widget.grid_columnconfigure(index, minsize=minsize, weight=weight)

    def _attach_row_bindtag(self, widget):
        """Route events from CTk widgets and their native children through row handlers."""
        tags = widget.bindtags()
        if self._row_bindtag not in tags:
            widget.bindtags((self._row_bindtag,) + tags)
        for child in widget.winfo_children():
            self._attach_row_bindtag(child)

    def _bind_optional_touchpad(self, widget):
        """Bind Tk 9's touchpad event when the running Tk supports it."""
        if widget is None:
            return
        try:
            widget.bind("<TouchpadScroll>", self._touchpad_scroll, add="+")
        except tk.TclError:
            pass

    def _bind_optional_touchpad_class(self):
        try:
            self.bind_class(self._row_bindtag, "<TouchpadScroll>", self._touchpad_scroll)
        except tk.TclError:
            pass

    def _update_scrollregion(self, event=None):
        """Update canvas scrollregion only when content size actually changes."""
        bbox = self._canvas.bbox("all")
        if bbox != self._last_scrollregion:
            self._last_scrollregion = bbox
            if bbox:
                self._canvas.configure(scrollregion=bbox)

    def _on_canvas_resize(self, event=None):
        """Keep the inner body frame as wide as the canvas viewport."""
        self._canvas.itemconfig(self._win, width=event.width)

    def _scroll_wheel(self, event):
        """Preserve native macOS wheel and trackpad delta magnitude."""
        if sys.platform == "darwin":
            if event.delta:
                self._canvas.yview("scroll", -event.delta, "units")
        else:
            units = -3 if event.delta > 0 else 3
            self._canvas.yview_scroll(units, "units")
        return "break"

    def _scroll_wheel_linux(self, event):
        """Linux: Button-4 = scroll up, Button-5 = scroll down."""
        units = -3 if event.num == 4 else 3
        self._canvas.yview_scroll(units, "units")
        return "break"

    def _touchpad_scroll(self, event):
        """Apply Tk 9's packed vertical touchpad delta to the table canvas."""
        _, delta_y = _decode_touchpad_delta(event.delta)
        if delta_y:
            self._canvas.yview_scroll(delta_y, "units")
        return "break"

    def _click(self, event, idx):
        cmd = bool(event.state & 0x0010)   # Cmd on macOS
        shift = bool(event.state & 0x0001)  # Shift

        if shift and self._last_idx is not None:
            lo, hi = sorted([self._last_idx, idx])
            self.selected.update(range(lo, hi + 1))
        elif cmd:
            if idx in self.selected:
                self.selected.discard(idx)
            else:
                self.selected.add(idx)
        else:
            self.selected = {idx}

        self._last_idx = idx
        self._repaint()
        if self._on_select:
            self._on_select()

    def _menu(self, event, idx):
        if idx not in self.selected:
            self.selected = {idx}
            self._repaint()
        if self._on_menu:
            self._on_menu(event)

    def _repaint(self):
        for i in range(len(self.rows)):
            self._apply_row_bg(i)

    def _apply_row_bg(self, idx):
        rf = self.rows[idx][0]
        if idx in self.selected:
            rf.configure(fg_color=C.BG_SEL)
        else:
            rf.configure(fg_color=C.BG_ROW_ALT if idx % 2 else C.BG)

    # ── Event delegation handlers ──

    @staticmethod
    def _get_row_idx(event):
        """Walk up from event.widget to find a frame with .idx attribute."""
        w = event.widget
        while w:
            idx = getattr(w, "idx", None)
            if idx is not None:
                return idx
            w = w.master
        return None

    def _on_body_click(self, event):
        idx = self._get_row_idx(event)
        if idx is not None:
            self._click(event, idx)
        return "break"

    def _on_body_menu(self, event):
        idx = self._get_row_idx(event)
        if idx is not None:
            self._menu(event, idx)
        return "break"

    def _on_body_enter(self, event):
        idx = self._get_row_idx(event)
        if idx is not None and idx not in self.selected:
            self.rows[idx][0].configure(fg_color=C.BG_HOVER)

    def _on_body_leave(self, event):
        idx = self._get_row_idx(event)
        if idx is not None:
            self._apply_row_bg(idx)

    @staticmethod
    def _col_label(key):
        return {"num": "序号", "path": "文件路径", "size": "大小",
                "mtime": "修改时间", "status": "状态"}.get(key, key)

    @staticmethod
    def _tag_color(col, tags):
        if col == "status":
            if "duplicate" in tags:
                return C.RED
            if "original" in tags:
                return C.GREEN
        if col == "path":
            return C.TEXT
        return C.TEXT2


# ════════════════════════════════════════════════════════════
#  Main Application
# ════════════════════════════════════════════════════════════

class WxCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"WxCleaner {__version__} - 微信重复文件清理工具")
        self.root.geometry("1100x800")
        self.root.minsize(900, 600)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root.configure(fg_color=C.BG)

        # icon
        try:
            icon_path = "icon.ico"
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # state
        self.duplicates = {}
        self.scanning = False
        self._cancel_event = threading.Event()
        self._closing = False

        # scan path
        default_path = ""
        if sys.platform == "darwin":
            default_path = os.path.expanduser(
                "~/Library/Containers/com.tencent.xinWeChat/"
            )
        self.scan_path = tk.StringVar(value=default_path)

        self._setup_ui()
        self._setup_keyboard_shortcuts()

        # Graceful shutdown: stop background threads on window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ────────────────────────────────────────────────────────
    #  UI
    # ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main = ctk.CTkFrame(self.root, fg_color=C.BG, corner_radius=0)
        main.pack(fill="both", expand=True, padx=S.PAD, pady=S.PAD)

        self._build_toolbar(main)
        ctk.CTkFrame(main, height=1, fg_color=C.BORDER).pack(fill="x", pady=(S.GAP, 0))
        self._build_summary(main)
        self._build_table(main)
        ctk.CTkFrame(main, height=1, fg_color=C.BORDER).pack(fill="x", pady=(S.GAP, 0))
        self._build_bottom(main)

    # ---- Toolbar ----

    def _build_toolbar(self, parent):
        sec = ctk.CTkFrame(parent, fg_color=C.BG, corner_radius=0)
        sec.pack(fill="x")

        ctk.CTkLabel(
            sec, text="扫描设置", font=T.TITLE, text_color=C.TEXT,
        ).pack(anchor="w")

        row = ctk.CTkFrame(sec, fg_color=C.BG, corner_radius=0)
        row.pack(fill="x", pady=(S.COMP, 0))

        ctk.CTkLabel(
            row, text="路径", font=T.BODY, text_color=C.TEXT2, width=40,
        ).pack(side="left", padx=(0, 8))

        self.entry = ctk.CTkEntry(
            row, textvariable=self.scan_path, font=T.BODY,
            height=S.BTN_H, border_color=C.BORDER,
            fg_color=C.BG_SEC, text_color=C.TEXT,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, S.COMP))

        self.btn_browse = ctk.CTkButton(
            row, text="浏览", font=T.BODY,
            width=80, height=S.BTN_H, corner_radius=8,
            fg_color=C.BG, text_color=C.TEXT, border_color=C.BORDER,
            border_width=1, hover_color=C.BG_SEC,
            command=self.browse_folder,
        )
        self.btn_browse.pack(side="left", padx=(0, 8))

        self.btn_scan = ctk.CTkButton(
            row, text="开始扫描", font=T.BODY,
            width=100, height=S.BTN_H, corner_radius=8,
            fg_color=C.ACCENT, hover_color=C.ACCENT_HOV,
            text_color="white",
            command=self.start_scan_thread,
        )
        self.btn_scan.pack(side="left", padx=(0, 8))

        self.btn_cancel = ctk.CTkButton(
            row, text="取消", font=T.BODY,
            width=80, height=S.BTN_H, corner_radius=8,
            fg_color=C.BG, text_color=C.TEXT2, border_color=C.BORDER,
            border_width=1, hover_color=C.BG_SEC,
            command=self.cancel_scan,
        )
        # hidden until a scan starts

    # ---- Summary ----

    def _build_summary(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=C.BG, corner_radius=0)
        bar.pack(fill="x", pady=(S.GAP, S.COMP))

        self.summary_label = ctk.CTkLabel(
            bar, text="", font=T.CAPTION, text_color=C.TEXT2,
        )
        self.summary_label.pack(side="left")

        self.btn_select_all = ctk.CTkButton(
            bar, text="全选重复项", font=T.BODY,
            width=110, height=30, corner_radius=6,
            fg_color=C.BG, text_color=C.ORANGE,
            border_color=C.ORANGE, border_width=1,
            hover_color="#FFF8E6",
            command=self.select_all_duplicates,
        )
        # hidden until results appear

    # ---- Table ----

    def _build_table(self, parent):
        cols = ("num", "path", "size", "mtime", "status")
        widths = (60, 0, 110, 170, 80)  # path width=0 means expand

        self.tree = FileTable(
            parent, columns=cols, widths=widths,
            on_select=self.on_tree_select,
            on_menu=self.show_menu,
        )
        self.tree.pack(fill="both", expand=True)

        # context menu
        self.menu = tk.Menu(
            self.root, tearoff=0,
            bg=C.BG, fg=C.TEXT,
            activebackground=C.ACCENT, activeforeground="white",
            font=T.BODY, borderwidth=1, relief="solid",
        )
        self.menu.add_command(label="打开文件位置", command=self.open_file_location)
        self.menu.add_separator()
        self.menu.add_command(label="保留此文件 (设为绿色)", command=self.unmark_item)
        self.menu.add_command(label="标记为删除 (设为红色)", command=self.mark_item)

    # ---- Bottom ----

    def _build_bottom(self, parent):
        bottom = ctk.CTkFrame(parent, fg_color=C.BG, corner_radius=0)
        bottom.pack(fill="x", pady=(S.GAP, 0))

        # progress bar (thin)
        self.progress = ctk.CTkProgressBar(
            bottom, orientation="horizontal", height=4,
            fg_color=C.BG_SEC, progress_color=C.ACCENT,
            border_color=C.BG_SEC, corner_radius=2,
        )
        self.progress.pack(fill="x", pady=(0, S.COMP))
        self.progress.set(0)

        # info row
        info = ctk.CTkFrame(bottom, fg_color=C.BG, corner_radius=0)
        info.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            info, text="准备就绪", font=T.CAPTION, text_color=C.TEXT2,
        )
        self.status_label.pack(side="left")

        self.selection_label = ctk.CTkLabel(
            info, text="", font=T.CAPTION_B, text_color=C.RED,
        )
        self.selection_label.pack(side="left", padx=(20, 0))

        self.btn_delete = ctk.CTkButton(
            info, text="移至回收站", font=T.BODY,
            width=120, height=S.BTN_H, corner_radius=8,
            fg_color=C.RED, hover_color=C.RED_HOV,
            text_color="white",
            command=self.delete_selected,
        )
        self.btn_delete.pack(side="right")

    # ────────────────────────────────────────────────────────
    #  Window lifecycle & keyboard shortcuts
    # ────────────────────────────────────────────────────────

    def _on_closing(self):
        self._closing = True
        self._cancel_event.set()
        self.root.destroy()

    def _setup_keyboard_shortcuts(self):
        self.root.bind("<Command-w>", lambda e: self._on_closing())
        self.root.bind("<Command-q>", lambda e: self._on_closing())
        self.root.bind("<Command-b>", lambda e: self.browse_folder())
        self.root.bind("<Return>", lambda e: self.start_scan_thread())
        self.root.bind("<Escape>", lambda e: self.cancel_scan() if self.scanning else None)

    # ────────────────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────────────────

    @staticmethod
    def _format_size(size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    @staticmethod
    def _parse_size(size_str):
        try:
            parts = str(size_str).split()
            if len(parts) == 2:
                val = float(parts[0])
                mult = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
                return val * mult.get(parts[1], 0)
        except Exception:
            pass
        return 0

    # ────────────────────────────────────────────────────────
    #  Core functionality (all preserved from original)
    # ────────────────────────────────────────────────────────

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.scan_path.set(path)

    def start_scan_thread(self):
        if self.scanning:
            return

        path = self.scan_path.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("警告", "请选择有效的文件夹")
            return

        self._cancel_event.clear()
        self.scanning = True
        self.status_label.configure(text="正在初始化...", text_color=C.ACCENT)
        self.progress.set(0)
        self.tree.clear()
        self.selection_label.configure(text="")
        self.summary_label.configure(text="")
        self.btn_select_all.pack_forget()
        self.btn_scan.configure(state="disabled", text="扫描中...")
        self.btn_cancel.configure(state="normal")
        self.btn_cancel.pack(side="left")

        threading.Thread(target=self.run_scan, args=(path,), daemon=True).start()

    def cancel_scan(self):
        self._cancel_event.set()
        self.status_label.configure(text="正在取消...", text_color=C.ORANGE)
        self.btn_cancel.configure(state="disabled")

    def run_scan(self, path):
        def progress_callback(current, total, status_text):
            if self._cancel_event.is_set() or self._closing:
                return
            def _update():
                self.status_label.configure(text=status_text, text_color=C.TEXT2)
                if total > 0:
                    self.progress.stop()
                    pct = (current / total) * 100
                    self.progress.set(min(pct / 100, 1.0))
            self.root.after(0, _update)

        try:
            if self._cancel_event.is_set():
                return
            self.duplicates = find_duplicates(path, progress_callback=progress_callback,
                                               cancel_event=self._cancel_event)
            if self._cancel_event.is_set():
                self.root.after(0, self._scan_cancelled)
            else:
                self.root.after(0, self.update_results)
        except Exception as error:
            error_text = str(error)

            def _error():
                if self._closing:
                    return
                messagebox.showerror("错误", f"扫描出错: {error_text}")
                self.status_label.configure(text="扫描失败", text_color=C.RED)
                self.scanning = False
                self._scan_cleanup()
            self.root.after(0, _error)

    def _scan_cancelled(self):
        self.status_label.configure(text="扫描已取消", text_color=C.ORANGE)
        self.scanning = False
        self._scan_cleanup()

    def _scan_cleanup(self):
        self.progress.stop()
        self.btn_scan.configure(state="normal", text="开始扫描")
        self.btn_cancel.pack_forget()

    def update_results(self):
        if self._closing:
            return
        self.scanning = False
        self.progress.stop()
        self.progress.set(1.0)
        self._scan_cleanup()

        total_groups = len(self.duplicates)
        total_files = sum(len(p) for p in self.duplicates.values())
        total_dup_size = 0

        count = 1
        for h, paths in self.duplicates.items():
            paths.sort(key=lambda x: len(x))

            for i, p in enumerate(paths):
                try:
                    stat = os.stat(p)
                    size = stat.st_size
                    size_str = self._format_size(size)
                    mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                except Exception:
                    size = 0
                    size_str = "未知"
                    mtime_str = "未知"

                if i > 0:
                    total_dup_size += size

                status = "保留" if i == 0 else "重复"
                tags = ("original",) if i == 0 else ("duplicate",)

                self.tree.insert(
                    values={"num": count, "path": p, "size": size_str,
                            "mtime": mtime_str, "status": status},
                    tags=tags,
                )
                count += 1

        # summary
        self.summary_label.configure(
            text=f"共 {total_groups} 组重复  ·  可释放 {self._format_size(total_dup_size)}"
        )
        self.btn_select_all.pack(side="right")

        self.status_label.configure(
            text=f"完成 — 找到 {total_groups} 组重复，共 {total_files} 个文件",
            text_color=C.GREEN,
        )

    def on_tree_select(self):
        selected_items = self.tree.selection()
        count = len(selected_items)
        total_size = 0.0

        for idx in selected_items:
            size_str = self.tree.item_values(idx, "size")
            total_size += self._parse_size(size_str)

        size_disp = self._format_size(total_size)
        self.selection_label.configure(text=f"已选中: {count} 个文件 ({size_disp})")

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def open_file_location(self):
        selected = self.tree.selection()
        if not selected:
            return
        path = self.tree.item_values(selected[0], "path")
        try:
            file_path = str(path)
            if sys.platform == "darwin":
                # macOS: "open -R" reveals and selects the file in Finder
                subprocess.Popen(["open", "-R", file_path])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", file_path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件位置: {e}")

    def unmark_item(self):
        for idx in self.tree.selection():
            self.tree.set_values(idx, {"status": "保留"})
            self.tree.set_tags(idx, ("original",))
        self.on_tree_select()

    def mark_item(self):
        for idx in self.tree.selection():
            self.tree.set_values(idx, {"status": "重复"})
            self.tree.set_tags(idx, ("duplicate",))
        self.on_tree_select()

    def select_all_duplicates(self):
        self.tree.selection_remove()
        items_to_select = []
        for idx in self.tree.get_children():
            if self.tree.item_values(idx, "status") == "重复":
                items_to_select.append(idx)
        if items_to_select:
            self.tree.selection_add(items_to_select)
        self.on_tree_select()

    def delete_selected(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("未选择", "请先在表格中选择要删除的项目")
            return

        count = len(selected_items)
        if not messagebox.askyesno("确认删除", f"确定要将 {count} 个项目移至回收站吗？"):
            return

        file_paths = [self.tree.item_values(idx, "path") for idx in selected_items]
        deleted_paths, errors = move_to_trash(file_paths, send2trash)
        deleted_path_set = set(deleted_paths)

        # delete rows in reverse order to keep indices valid
        for idx in sorted(selected_items, reverse=True):
            path = self.tree.item_values(idx, "path")
            if path in deleted_path_set:
                self.tree.delete(idx)

        if errors:
            messagebox.showerror("部分操作失败", "\n".join(errors))

        remaining = sum(
            1 for idx in self.tree.get_children()
            if self.tree.item_values(idx, "status") == "重复"
        )
        self.summary_label.configure(text=f"已清理，剩余 {remaining} 个重复文件")
        self.on_tree_select()
