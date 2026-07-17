from datetime import datetime, timezone

from core.tracking import filter_pending_files

MTIME_A = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
MTIME_B = datetime(2026, 7, 11, 9, 30, 0, tzinfo=timezone.utc)


def _file(rel_path, mtime, size_bytes):
    return {"rel_path": rel_path, "mtime": mtime, "size_bytes": size_bytes}


def test_file_never_seen_is_kept():
    files = [_file("a.json", MTIME_A, 100)]
    tracked = {}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_file_unchanged_mtime_and_size_is_skipped():
    files = [_file("a.json", MTIME_A, 100)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == []


def test_file_with_different_mtime_is_kept():
    files = [_file("a.json", MTIME_B, 100)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_file_with_same_mtime_but_different_size_is_kept():
    files = [_file("a.json", MTIME_A, 999)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_full_rehash_keeps_all_files_regardless_of_tracking():
    files = [_file("a.json", MTIME_A, 100), _file("b.json", MTIME_B, 200)]
    tracked = {"a.json": (MTIME_A, 100), "b.json": (MTIME_B, 200)}

    result = filter_pending_files(files, tracked, full_rehash=True)

    assert result == files
