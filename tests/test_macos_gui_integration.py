from pathlib import Path


SOURCE = Path(__file__).parents[1] / "source" / "wx_gui.py"


def test_gui_uses_safe_trash_helper_and_macos_folder_opening():
    source = SOURCE.read_text()

    assert "from file_actions import move_to_trash" in source
    assert "def delete_selected(self):" in source
    assert "move_to_trash(file_paths, send2trash)" in source
    assert "close window" in source or "WM_DELETE_WINDOW" in source
    assert '剩余 {remaining} 个重复文件' in source
    assert 'if sys.platform == "darwin":' in source
    assert 'subprocess.Popen(["open", "-R", file_path])' in source
