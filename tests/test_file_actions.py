from file_actions import move_to_trash


def test_move_to_trash_returns_only_paths_moved_successfully(tmp_path):
    good = tmp_path / "good.txt"
    missing = tmp_path / "missing.txt"
    good.write_text("content")
    moved = []

    deleted, errors = move_to_trash([str(good), str(missing)], moved.append)

    assert deleted == [str(good)]
    assert moved == [str(good)]
    assert errors == [f"路径无效或不存在: {missing}"]


def test_move_to_trash_rejects_blank_path_without_calling_sender():
    moved = []

    deleted, errors = move_to_trash([""], moved.append)

    assert deleted == []
    assert moved == []
    assert errors == ["路径无效或不存在: "]
