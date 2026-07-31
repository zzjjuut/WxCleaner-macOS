import os
import threading
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "source"))

from scanner import find_duplicates, calculate_hash


def test_no_duplicates_returns_empty(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    result = find_duplicates(str(tmp_path))
    assert result == {}


def test_identical_files_found_as_duplicates(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same content")
    b.write_text("same content")

    result = find_duplicates(str(tmp_path))
    assert len(result) == 1
    paths = list(result.values())[0]
    assert len(paths) == 2
    assert str(a) in paths
    assert str(b) in paths


def test_multiple_duplicate_groups(tmp_path):
    # Group 1: 3 identical files
    for f in ("g1_a.txt", "g1_b.txt", "g1_c.txt"):
        (tmp_path / f).write_text("group1")

    # Group 2: 2 identical files
    (tmp_path / "g2_a.txt").write_text("group2")
    (tmp_path / "g2_b.txt").write_text("group2")

    # A unique file
    (tmp_path / "unique.txt").write_text("unique")

    result = find_duplicates(str(tmp_path))
    assert len(result) == 2
    all_paths = [p for paths in result.values() for p in paths]
    assert len(all_paths) == 5  # 3 + 2


def test_empty_file_not_duplicated(tmp_path):
    (tmp_path / "empty1.txt").write_text("")
    (tmp_path / "empty2.txt").write_text("")
    # Both are empty (size=0) and should be skipped
    (tmp_path / "real.txt").write_text("content")

    result = find_duplicates(str(tmp_path))
    assert result == {}


def test_nested_directories(tmp_path):
    d1 = tmp_path / "sub1"
    d2 = tmp_path / "sub2"
    d1.mkdir()
    d2.mkdir()

    (d1 / "file.txt").write_text("same")
    (d2 / "file.txt").write_text("same")

    result = find_duplicates(str(tmp_path))
    assert len(result) == 1


def test_cancel_event_stops_scan(tmp_path):
    cancel = threading.Event()
    # Create many files to give the scanner something to process
    for i in range(100):
        (tmp_path / f"file_{i}.txt").write_text(f"content_{i}")

    # Cancel immediately
    cancel.set()
    result = find_duplicates(str(tmp_path), cancel_event=cancel)
    assert result == {}


def test_progress_callback_called(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("hello")

    calls = []

    def cb(current, total, text):
        calls.append((current, total, text))

    find_duplicates(str(tmp_path), progress_callback=cb)
    assert len(calls) > 0
    # Should have at least a "starting" and "finished" progress update
    assert any("共找到" in c[2] for c in calls)
    assert any("全量校验" in c[2] or "完成" in c[2] for c in calls)


def test_calculate_hash_different_files(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"\x00" * 2000)
    b.write_bytes(b"\x01" * 2000)

    h1 = calculate_hash(str(a), partial=False)
    h2 = calculate_hash(str(b), partial=False)
    assert h1 != h2


def test_calculate_hash_partial_vs_full(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\xAB" * 10000)

    partial = calculate_hash(str(f), partial=True)
    full = calculate_hash(str(f), partial=False)
    assert partial is not None
    assert full is not None
    # Partial is only first 1024 bytes, so it should be different from full
    assert partial != full


def test_duplicate_paths_are_sorted_for_stable_display(tmp_path):
    z_path = tmp_path / "z.txt"
    a_path = tmp_path / "a.txt"
    z_path.write_text("same")
    a_path.write_text("same")

    result = find_duplicates(str(tmp_path))
    paths = next(iter(result.values()))

    assert paths == sorted(paths)
