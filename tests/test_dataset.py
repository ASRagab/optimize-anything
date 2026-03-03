from __future__ import annotations

from pathlib import Path

import pytest

from optimize_anything.dataset import load_dataset


def test_load_dataset_valid_jsonl(tmp_path: Path):
    path = tmp_path / "data.jsonl"
    path.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")

    data = load_dataset(str(path))

    assert data == [{"a": 1}, {"b": 2}]


def test_load_dataset_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "data.jsonl"
    path.write_text('\n{"a": 1}\n\n{"b": 2}\n\n', encoding="utf-8")

    data = load_dataset(str(path))

    assert data == [{"a": 1}, {"b": 2}]


def test_load_dataset_malformed_json_line_reports_line_number(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\n{"bad":\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"line 2"):
        load_dataset(str(path))


def test_load_dataset_rejects_non_object_records(tmp_path: Path):
    arr_path = tmp_path / "arr.jsonl"
    arr_path.write_text('[1, 2]\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"expected JSON object"):
        load_dataset(str(arr_path))

    str_path = tmp_path / "str.jsonl"
    str_path.write_text('"hello"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"expected JSON object"):
        load_dataset(str(str_path))

    num_path = tmp_path / "num.jsonl"
    num_path.write_text('42\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"expected JSON object"):
        load_dataset(str(num_path))


def test_load_dataset_empty_file(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    data = load_dataset(str(path))

    assert data == []


def test_load_dataset_rejects_more_than_10k_records(tmp_path: Path):
    path = tmp_path / "large.jsonl"
    lines = ['{"i": %d}' % i for i in range(10_001)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"maximum 10000"):
        load_dataset(str(path))


def test_load_dataset_utf8_encoding(tmp_path: Path):
    path = tmp_path / "utf8.jsonl"
    path.write_text('{"text": "مرحبا"}\n{"emoji": "🦞"}\n', encoding="utf-8")

    data = load_dataset(str(path))

    assert data == [{"text": "مرحبا"}, {"emoji": "🦞"}]
