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
