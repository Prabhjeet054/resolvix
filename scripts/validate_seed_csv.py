"""Validate data/tickets_seed.csv structure and value distributions."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "tickets_seed.csv"

EXPECTED_COLUMNS = [
    "description",
    "language_code",
    "category_name",
    "resolution",
    "priority",
]
VALID_CATEGORIES = {
    "Billing",
    "Technical",
    "Account",
    "Refund",
    "Login",
    "General",
}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
REQUIRED_LANGUAGES = {"en", "hi", "ta"}


def validate_seed_csv(csv_path: Path = CSV_PATH) -> None:
    """Load the seed CSV and assert schema / distribution requirements."""
    df = pd.read_csv(csv_path)

    assert len(df) >= 20, f"Expected at least 20 rows, got {len(df)}"
    assert list(df.columns) == EXPECTED_COLUMNS, (
        f"Expected columns {EXPECTED_COLUMNS}, got {list(df.columns)}"
    )
    print(f"Loaded {csv_path} — {len(df)} rows, columns={list(df.columns)}")

    print("\nlanguage_code value_counts():")
    lang_counts = df["language_code"].value_counts()
    print(lang_counts.to_string())
    present_langs = set(lang_counts.index)
    missing_langs = REQUIRED_LANGUAGES - present_langs
    assert not missing_langs, f"Missing languages: {sorted(missing_langs)}"
    low_langs = {
        lang: int(count)
        for lang, count in lang_counts.items()
        if lang in REQUIRED_LANGUAGES and count < 5
    }
    assert not low_langs, f"Languages below 5 rows: {low_langs}"
    print("Language distribution OK (all of en/hi/ta present, none below 5).")

    print("\ncategory_name value_counts():")
    category_counts = df["category_name"].value_counts()
    print(category_counts.to_string())
    invalid_categories = sorted(set(df["category_name"]) - VALID_CATEGORIES)
    assert not invalid_categories, (
        f"Invalid category_name values found: {invalid_categories}"
    )
    print("Category values OK (all match the 6 seeded categories).")

    print("\npriority value_counts():")
    priority_counts = df["priority"].value_counts()
    print(priority_counts.to_string())
    missing_priorities = VALID_PRIORITIES - set(priority_counts.index)
    assert not missing_priorities, (
        f"Missing priority levels: {sorted(missing_priorities)}"
    )
    print("Priority distribution OK (LOW/MEDIUM/HIGH/URGENT all present).")

    empty_description = df["description"].isna() | (
        df["description"].astype(str).str.strip() == ""
    )
    empty_resolution = df["resolution"].isna() | (
        df["resolution"].astype(str).str.strip() == ""
    )
    empty_desc_rows = df.index[empty_description].tolist()
    empty_res_rows = df.index[empty_resolution].tolist()

    print("\nEmpty cell check:")
    if empty_desc_rows or empty_res_rows:
        print(f"  Empty description row indexes: {empty_desc_rows}")
        print(f"  Empty resolution row indexes: {empty_res_rows}")
        raise AssertionError(
            "Found empty description/resolution cells; see indexes above."
        )
    print("  No completely empty description or resolution cells.")

    print("\nAll seed CSV validation checks passed.")


if __name__ == "__main__":
    try:
        validate_seed_csv()
    except AssertionError as exc:
        print(f"\nVALIDATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
