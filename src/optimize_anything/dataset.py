"""Dataset loading utilities for JSONL train/validation sets."""

from __future__ import annotations

import json
from pathlib import Path


_MAX_RECORDS = 10_000


def load_dataset(path: str) -> list[dict]:
    """Load and validate a JSONL dataset file.

    Rules:
    - UTF-8 text file
    - One JSON object per non-blank line
    - Blank lines are skipped
    - Maximum 10,000 records

    Raises:
        ValueError: if the file cannot be read/decoded or validation fails.
    """
    records: list[dict] = []
    dataset_path = Path(path)

    try:
        with dataset_path.open("r", encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                if not raw_line.strip():
                    continue

                try:
                    parsed = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in dataset '{path}' at line {line_number}: {exc.msg}"
                    ) from exc

                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"Invalid record in dataset '{path}' at line {line_number}: expected JSON object"
                    )

                records.append(parsed)
                if len(records) > _MAX_RECORDS:
                    raise ValueError(
                        f"Dataset '{path}' has too many records: maximum {_MAX_RECORDS}"
                    )
    except UnicodeDecodeError as exc:
        raise ValueError(f"Dataset '{path}' is not valid UTF-8") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read dataset '{path}': {exc}") from exc

    return records
