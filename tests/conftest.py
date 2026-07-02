import os
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def data_dir(project_root):
    return project_root / "data"


@pytest.fixture
def db_path(data_dir, tmp_path):
    test_db = tmp_path / "test.duckdb"
    return str(test_db)
