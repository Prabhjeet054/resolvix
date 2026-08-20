"""Smoke tests for the ticket-similarity-finder project layout.

Verifies that required folders, root files, and db.connection.get_connection
exist without connecting to Oracle.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FOLDERS = ("db", "embeddings", "app", "data", "tests", "scripts")
EXPECTED_ROOT_FILES = (".env.example", "requirements.txt", "README.md", ".gitignore")


def test_expected_folders_exist():
    """Assert all required project directories exist."""
    missing = [name for name in EXPECTED_FOLDERS if not (PROJECT_ROOT / name).is_dir()]
    assert not missing, f"Missing folders: {missing}"


def test_expected_root_files_exist():
    """Assert required root configuration files exist."""
    missing = [name for name in EXPECTED_ROOT_FILES if not (PROJECT_ROOT / name).is_file()]
    assert not missing, f"Missing files: {missing}"


def test_get_connection_is_callable():
    """Assert db/connection.py exports a callable get_connection."""
    connection_path = PROJECT_ROOT / "db" / "connection.py"
    assert connection_path.is_file(), "db/connection.py is missing"

    spec = spec_from_file_location("db_connection", connection_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "get_connection"), "get_connection is not exported"
    assert callable(module.get_connection), "get_connection is not callable"
