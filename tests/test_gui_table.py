import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "source"))


def _make_root():
    try:
        import customtkinter as ctk
        import tkinter as tk
    except ModuleNotFoundError as error:
        if error.name == "_tkinter":
            pytest.skip("Tk support unavailable in this Python")
        raise

    try:
        root = ctk.CTk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.geometry("500x220")
    root.withdraw()
    return root


@pytest.fixture(scope="module")
def tk_root():
    root = _make_root()
    yield root
    root.destroy()


def _import_file_table():
    try:
        from wx_gui import FileTable
    except ModuleNotFoundError as error:
        if error.name == "_tkinter":
            pytest.skip("Tk support unavailable in this Python")
        raise
    return FileTable


def test_touchpad_delta_decoder_handles_signed_packed_values():
    from wx_gui import _decode_touchpad_delta

    raw_delta = ((7 & 0xFFFF) << 16) | ((-12) & 0xFFFF)

    assert _decode_touchpad_delta(raw_delta) == (7, -12)


def test_touchpad_scroll_applies_decoded_vertical_delta():
    from wx_gui import FileTable

    calls = []
    table = FileTable.__new__(FileTable)
    table._canvas = SimpleNamespace(
        yview_scroll=lambda amount, unit: calls.append((amount, unit)),
    )
    raw_delta = ((3 & 0xFFFF) << 16) | ((-9) & 0xFFFF)

    result = table._touchpad_scroll(SimpleNamespace(delta=raw_delta))

    assert result == "break"
    assert calls == [(-9, "units")]


def _make_scrollable_table(root):
    FileTable = _import_file_table()
    table = FileTable(
        root,
        columns=("num", "path", "status"),
        widths=(60, 0, 80),
    )
    table.pack(fill="both", expand=True)
    for i in range(60):
        table.insert(
            {"num": i + 1, "path": f"/tmp/file-{i}.txt", "status": "重复"},
            tags=("duplicate",),
        )
    root.update_idletasks()
    return table


def _make_full_table(root):
    root.geometry("1100x700")
    FileTable = _import_file_table()
    table = FileTable(
        root,
        columns=("num", "path", "size", "mtime", "status"),
        widths=(60, 0, 110, 170, 80),
    )
    table.pack(fill="both", expand=True)
    table.insert(
        {
            "num": 1,
            "path": "/Users/m2222/Library/Containers/com.tencent.xinWeChat/Data/Library/Caches/profiles/game/Code Cache/wasm/index",
            "size": "24.00 B",
            "mtime": "2026-07-30 22:58:49",
            "status": "重复",
        },
        tags=("duplicate",),
    )
    table.insert(
        {
            "num": 2,
            "path": "/tmp/short.txt",
            "size": "1.00 KB",
            "mtime": "2026-07-29 12:05:40",
            "status": "保留",
        },
        tags=("original",),
    )
    root.update_idletasks()
    return table


def _first_tk_child(widget, class_name):
    for child in widget.winfo_children():
        if child.winfo_class() == class_name:
            return child
    raise AssertionError(f"No {class_name} child found in {widget}")


def test_shared_header_row_geometry(tk_root):
    root = tk_root
    table = None
    try:
        table = _make_full_table(root)
        header_cells = table._header.winfo_children()
        row_cells = [table.rows[0][1][col] for col in table.col_keys]

        assert [int(table._header.grid_columnconfigure(i, "minsize")) for i in range(5)] == [
            60, 180, 110, 170, 80,
        ]
        assert len(header_cells) == len(row_cells) == 5
        for header_cell, row_cell in zip(header_cells, row_cells):
            assert header_cell.winfo_x() == row_cell.winfo_x()
            assert header_cell.winfo_width() == row_cell.winfo_width()
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_path_column_resizes_without_moving_fixed_columns(tk_root):
    root = tk_root
    table = None
    original_geometry = root.geometry()
    try:
        root.deiconify()
        table = _make_full_table(root)
        fixed_columns = ("num", "size", "mtime", "status")

        root.geometry("760x700")
        root.update_idletasks()
        narrow_widths = {
            col: table.rows[0][1][col].winfo_width() for col in table.col_keys
        }

        root.geometry("1100x700")
        root.update_idletasks()
        wide_widths = {
            col: table.rows[0][1][col].winfo_width() for col in table.col_keys
        }

        assert wide_widths["path"] > narrow_widths["path"]
        for col in fixed_columns:
            assert wide_widths[col] == narrow_widths[col]
    finally:
        if table is not None:
            table.destroy()
        root.geometry(original_geometry)
        root.withdraw()
        root.update_idletasks()


def test_clicking_cell_text_selects_the_row(tk_root):
    root = tk_root
    table = None
    try:
        FileTable = _import_file_table()
        selected = []
        table = FileTable(
            root,
            columns=("num", "path", "status"),
            widths=(60, 0, 80),
            on_select=lambda: selected.append(table.selection()),
        )
        table.pack(fill="both", expand=True)
        table.insert({"num": 1, "path": "/tmp/a.txt", "status": "重复"}, tags=("duplicate",))
        root.update_idletasks()

        table.rows[0][1]["path"].event_generate("<Button-1>", x=5, y=5)
        root.update()

        assert table.selection() == [0]
        assert selected == [[0]]
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_mousewheel_on_body_background_canvas_scrolls_rows(tk_root):
    root = tk_root
    table = None
    try:
        table = _make_scrollable_table(root)
        assert table._canvas.yview()[0] == 0.0

        table._body._canvas.event_generate("<MouseWheel>", delta=-120, x=5, y=5)
        root.update()

        assert table._canvas.yview()[0] > 0.0
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_mousewheel_on_internal_label_text_scrolls_rows(tk_root):
    root = tk_root
    table = None
    try:
        table = _make_scrollable_table(root)
        text_widget = _first_tk_child(table.rows[0][1]["path"], "Label")
        assert table._canvas.yview()[0] == 0.0

        text_widget.event_generate("<MouseWheel>", delta=-120, x=5, y=5)
        root.update()

        assert table._canvas.yview()[0] > 0.0
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_macos_canvas_uses_native_scroll_increment(tk_root):
    table = None
    try:
        table = _make_scrollable_table(tk_root)

        assert int(table._canvas.cget("yscrollincrement")) == 8
    finally:
        if table is not None:
            table.destroy()
        tk_root.update_idletasks()


def test_macos_scroll_preserves_delta_magnitude(tk_root):
    root = tk_root
    table = None
    try:
        table = _make_scrollable_table(root)
        row_label = _first_tk_child(table.rows[0][1]["path"], "Label")

        table._canvas.yview_moveto(0)
        row_label.event_generate("<MouseWheel>", delta=-1, x=5, y=5)
        root.update()
        small_delta_position = table._canvas.yview()[0]

        table._canvas.yview_moveto(0)
        row_label.event_generate("<MouseWheel>", delta=-12, x=5, y=5)
        root.update()
        large_delta_position = table._canvas.yview()[0]

        assert large_delta_position > small_delta_position
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_supported_touchpad_event_scrolls_rows(tk_root):
    root = tk_root
    table = None
    try:
        table = _make_scrollable_table(root)
        try:
            table.rows[0][1]["path"].event_generate(
                "<TouchpadScroll>", delta=(-12) & 0xFFFF, x=5, y=5,
            )
        except tk.TclError as error:
            if "bad event type or keysym" in str(error):
                pytest.skip("Tk build does not support TouchpadScroll")
            raise
        root.update()

        assert table._canvas.yview()[0] > 0.0
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()


def test_deleting_a_row_reindexes_later_cell_clicks(tk_root):
    root = tk_root
    table = None
    try:
        FileTable = _import_file_table()
        table = FileTable(
            root,
            columns=("num", "path", "status"),
            widths=(60, 0, 80),
        )
        table.pack(fill="both", expand=True)
        table.insert({"num": 1, "path": "/tmp/a.txt", "status": "保留"}, tags=("original",))
        table.insert({"num": 2, "path": "/tmp/b.txt", "status": "重复"}, tags=("duplicate",))
        root.update_idletasks()

        table.delete(0)

        assert table._get_row_idx(SimpleNamespace(widget=table.rows[0][1]["path"])) == 0
        assert table.item_values(0, "path") == "/tmp/b.txt"
    finally:
        if table is not None:
            table.destroy()
        root.update_idletasks()
