from datetime import datetime

from core.discovery import discover_files


def test_discover_files_includes_rel_path_mtime_size(tmp_path):
    raw_dir = tmp_path / "raw"
    file_dir = raw_dir / "football_data_org" / "matches" / "2026-07-10"
    file_dir.mkdir(parents=True)
    file_path = file_dir / "PL_2025_120000_000000.json"
    file_path.write_text('{"a": 1}', encoding="utf-8")

    files = discover_files(raw_dir)

    assert len(files) == 1
    f = files[0]
    assert f["rel_path"] == "football_data_org/matches/2026-07-10/PL_2025_120000_000000.json"
    assert f["source"] == "football_data_org"
    assert f["entity_type"] == "matches"
    assert f["date"] == "2026-07-10"
    assert isinstance(f["mtime"], datetime)
    assert f["mtime"].tzinfo is not None
    assert f["size_bytes"] == file_path.stat().st_size
