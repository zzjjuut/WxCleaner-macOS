import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "source"))

try:
    import wx_gui
except ModuleNotFoundError as error:
    if error.name == "_tkinter":
        pytest.skip("Tk support unavailable in this Python", allow_module_level=True)
    raise


class FakeWidget:
    def __init__(self, **state):
        self.state = state
        self.packed = False

    def configure(self, **kwargs):
        self.state.update(kwargs)

    def pack(self, **kwargs):
        self.packed = True

    def pack_forget(self):
        self.packed = False


class FakeProgress(FakeWidget):
    def __init__(self):
        super().__init__()
        self.value = None
        self.stopped = False

    def stop(self):
        self.stopped = True

    def set(self, value):
        self.value = value


class DeferredRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, _delay, callback):
        self.callbacks.append(callback)


def _app_for_scan_start(tmp_path):
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app.scanning = False
    app._cancel_event = threading.Event()
    app.scan_path = SimpleNamespace(get=lambda: str(tmp_path))
    app.status_label = FakeWidget()
    app.progress = FakeProgress()
    app.tree = SimpleNamespace(clear=lambda: None)
    app.selection_label = FakeWidget()
    app.summary_label = FakeWidget()
    app.btn_select_all = FakeWidget()
    app.btn_scan = FakeWidget()
    app.btn_cancel = FakeWidget(state="disabled")
    return app


def test_starting_a_new_scan_reenables_cancel_button(tmp_path, monkeypatch):
    app = _app_for_scan_start(tmp_path)

    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            return None

    monkeypatch.setattr(wx_gui.threading, "Thread", FakeThread)

    app.start_scan_thread()

    assert app.btn_cancel.state["state"] == "normal"


def test_completed_scan_keeps_progress_at_one():
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app._closing = False
    app.scanning = True
    app.duplicates = {}
    app.progress = FakeProgress()
    app.btn_scan = FakeWidget()
    app.btn_cancel = FakeWidget()
    app.summary_label = FakeWidget()
    app.status_label = FakeWidget()
    app.btn_select_all = FakeWidget()
    app.root = SimpleNamespace(after=lambda *args: None)
    app.tree = SimpleNamespace(insert=lambda *args, **kwargs: None)

    app.update_results()

    assert app.progress.value == 1.0


def test_large_result_set_is_rendered_in_batches():
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app._closing = False
    app.scanning = True
    app.progress = FakeProgress()
    app.btn_scan = FakeWidget()
    app.btn_cancel = FakeWidget()
    app.summary_label = FakeWidget()
    app.status_label = FakeWidget()
    app.btn_select_all = FakeWidget()

    inserted = []

    def insert(values, tags):
        inserted.append(values)

    app.tree = SimpleNamespace(
        insert=insert,
        get_children=lambda: list(range(len(inserted))),
    )

    scheduled = []
    app.root = SimpleNamespace(after=lambda delay, cb: scheduled.append(cb))

    # 5 组 × 2 个文件 = 10 行；批大小临时压到 2
    app.duplicates = {f"hash-{i}": [f"/keep-{i}", f"/dup-{i}"] for i in range(5)}
    original_batch = wx_gui.WxCleanerApp.RENDER_BATCH
    wx_gui.WxCleanerApp.RENDER_BATCH = 2
    try:
        app.update_results()

        # 首批只插入 2 行，其余通过 root.after 调度
        assert len(inserted) == 2
        assert len(scheduled) == 1
        assert "正在显示结果" in app.status_label.state["text"]
        assert not app.btn_select_all.packed

        while scheduled:
            scheduled.pop()()

        assert len(inserted) == 10
        assert not scheduled
        assert app.btn_select_all.packed
        assert app.status_label.state["text"].startswith("完成")
    finally:
        wx_gui.WxCleanerApp.RENDER_BATCH = original_batch


def test_empty_selection_clears_selection_label():
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app.tree = SimpleNamespace(selection=lambda: [])
    app.selection_label = FakeWidget()

    app.on_tree_select()

    assert app.selection_label.state["text"] == ""


def test_selection_size_uses_exact_bytes():
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    rows = {
        0: {"bytes": 1024, "size": "1.00 KB"},
        1: {"bytes": 512, "size": "512.00 B"},
        2: {"bytes": "", "size": "未知"},  # stat 失败的行按 0 计
    }
    app.tree = SimpleNamespace(
        selection=lambda: [0, 1, 2],
        item_values=lambda idx, col: rows[idx].get(col, ""),
    )
    app.selection_label = FakeWidget()

    app.on_tree_select()

    assert app.selection_label.state["text"] == "已选中: 3 个文件 (1.50 KB)"


def test_delete_selected_reports_in_status_and_keeps_summary(tmp_path, monkeypatch):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    for f in (a, b, c):
        f.write_text("x")

    class FakeTree:
        def __init__(self):
            self.rows = [
                {"path": str(a), "status": "重复", "bytes": 10},
                {"path": str(b), "status": "重复", "bytes": 20},
                {"path": str(c), "status": "保留", "bytes": 5},
            ]
            self.selected = [0, 1]

        def selection(self):
            return list(self.selected)

        def item_values(self, idx, col=None):
            vals = self.rows[idx]
            return dict(vals) if col is None else vals.get(col, "")

        def get_children(self):
            return list(range(len(self.rows)))

        def delete(self, idx):
            self.rows.pop(idx)
            self.selected = [i if i < idx else i - 1 for i in self.selected if i != idx]

    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app.tree = FakeTree()
    app.summary_label = FakeWidget()
    app.summary_label.configure(text="共 1 组重复  ·  可释放 30.00 B")
    app.status_label = FakeWidget()
    app.selection_label = FakeWidget()

    monkeypatch.setattr(wx_gui, "send2trash", lambda path: None)
    monkeypatch.setattr(wx_gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    errors = []
    monkeypatch.setattr(wx_gui.messagebox, "showerror",
                        lambda title, message: errors.append(message))

    app.delete_selected()

    assert errors == []
    # 扫描统计不被删除结果覆盖，删除结果进状态栏
    assert app.summary_label.state["text"] == "共 1 组重复  ·  可释放 30.00 B"
    assert app.status_label.state["text"] == "已将 2 个文件移至回收站，剩余 0 个重复文件"
    # 全部选中项删除后选中区清空
    assert app.selection_label.state["text"] == ""


def test_batch_rendering_stops_after_window_close():
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app._closing = False
    app.scanning = True
    app.progress = FakeProgress()
    app.btn_scan = FakeWidget()
    app.btn_cancel = FakeWidget()
    app.summary_label = FakeWidget()
    app.status_label = FakeWidget()
    app.btn_select_all = FakeWidget()
    app.tree = SimpleNamespace(
        insert=lambda values, tags: None,
        get_children=lambda: [],
    )
    scheduled = []
    app.root = SimpleNamespace(after=lambda delay, cb: scheduled.append(cb))

    app.duplicates = {f"hash-{i}": [f"/keep-{i}", f"/dup-{i}"] for i in range(5)}
    original_batch = wx_gui.WxCleanerApp.RENDER_BATCH
    wx_gui.WxCleanerApp.RENDER_BATCH = 2
    try:
        app.update_results()
        app._closing = True

        while scheduled:
            scheduled.pop()()

        assert not scheduled
        assert not app.btn_select_all.packed
    finally:
        wx_gui.WxCleanerApp.RENDER_BATCH = original_batch


def test_deferred_scan_error_callback_keeps_exception_text(monkeypatch):
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app._cancel_event = threading.Event()
    app._closing = False
    app.scanning = True
    app.root = DeferredRoot()
    app.status_label = FakeWidget()
    app.btn_scan = FakeWidget()
    app.btn_cancel = FakeWidget()
    app.progress = FakeProgress()
    app._scan_cleanup = lambda: None
    errors = []

    def fail_scan(*args, **kwargs):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(wx_gui, "find_duplicates", fail_scan)
    monkeypatch.setattr(
        wx_gui.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.run_scan("/tmp")

    assert len(app.root.callbacks) == 1
    app.root.callbacks[0]()

    assert errors == [("错误", "扫描出错: permission denied")]
    assert app.status_label.state["text"] == "扫描失败"


def _app_for_open_location(path):
    app = wx_gui.WxCleanerApp.__new__(wx_gui.WxCleanerApp)
    app.tree = SimpleNamespace(
        selection=lambda: [0],
        item_values=lambda idx, col: path if col == "path" else "",
    )
    return app


def test_open_file_location_warns_when_file_is_gone(monkeypatch):
    app = _app_for_open_location("/nonexistent/file.txt")
    warnings = []
    monkeypatch.setattr(wx_gui.messagebox, "showwarning",
                        lambda title, message: warnings.append((title, message)))
    opened = []
    monkeypatch.setattr(wx_gui.subprocess, "run",
                        lambda *args, **kwargs: opened.append(args))

    app.open_file_location()

    assert warnings == [("提示", "文件已不存在（可能已被清理）：\n/nonexistent/file.txt")]
    assert opened == []


def test_open_file_location_reports_open_failure(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    app = _app_for_open_location(str(f))
    dialogs = []
    monkeypatch.setattr(wx_gui.messagebox, "showerror",
                        lambda title, message: dialogs.append((title, message)))
    monkeypatch.setattr(wx_gui.messagebox, "showwarning",
                        lambda title, message: dialogs.append((title, message)))
    monkeypatch.setattr(
        wx_gui.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=b"boom"),
    )

    app.open_file_location()

    assert dialogs == [("错误", "无法打开文件位置: boom")]


def test_open_file_location_succeeds_silently(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    app = _app_for_open_location(str(f))
    dialogs = []
    monkeypatch.setattr(wx_gui.messagebox, "showerror",
                        lambda title, message: dialogs.append((title, message)))
    monkeypatch.setattr(wx_gui.messagebox, "showwarning",
                        lambda title, message: dialogs.append((title, message)))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(wx_gui.subprocess, "run", fake_run)

    app.open_file_location()

    assert calls == [["open", "-R", str(f)]]
    assert dialogs == []
