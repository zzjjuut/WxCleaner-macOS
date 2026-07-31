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
    app.tree = SimpleNamespace(insert=lambda **kwargs: None)

    app.update_results()

    assert app.progress.value == 1.0


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
