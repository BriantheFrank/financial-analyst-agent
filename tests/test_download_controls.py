import time
from pathlib import Path

from sec_financials import _choose_instance_from_index, _is_skippable_artifact, prune_cache


def test_file_filter_skips_non_required_artifacts():
    max_size = 25 * 1024 * 1024
    assert _is_skippable_artifact("foo.pdf", 1024, max_size_bytes=max_size)
    assert _is_skippable_artifact("foo.zip", 1024, max_size_bytes=max_size)
    assert _is_skippable_artifact("image.png", 1024, max_size_bytes=max_size)
    assert not _is_skippable_artifact("instance_htm.xml", 1024, max_size_bytes=max_size)


def test_index_json_instance_selection_prefers_htm_and_instance_type():
    items = [
        {"name": "abc_cal.xml", "type": "EX-101.CAL", "size": 1000},
        {"name": "foo.xml", "type": "EX-101.INS", "size": 5000},
        {"name": "report_htm.xml", "type": "XML", "size": 2000},
    ]
    chosen = _choose_instance_from_index(items)
    assert chosen == "report_htm.xml"


def test_prune_cache_respects_age_and_size(tmp_path: Path):
    cache = tmp_path / "sec"
    cache.mkdir()
    old_file = cache / "old.bin"
    new_file = cache / "new.bin"
    old_file.write_bytes(b"a" * 300)
    new_file.write_bytes(b"b" * 300)

    old_ts = time.time() - (40 * 86400)
    new_ts = time.time()
    import os
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    prune_cache(cache_dir=str(cache), max_age_days=30, max_total_gb=0.0000002)

    assert not old_file.exists()
    remaining = [p for p in cache.rglob("*") if p.is_file()]
    assert sum(p.stat().st_size for p in remaining) <= int(0.0000002 * 1024 * 1024 * 1024)
