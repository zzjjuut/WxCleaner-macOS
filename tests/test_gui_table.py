import sys
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


def _first_tk_child(widget, class_name):
    for child in widget.winfo_children():
        if child.winfo_class() == class_name:
            return child
    raise AssertionError(f"No {class_name} child found in {widget}")


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
