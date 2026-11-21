from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.main import Settings, create_app


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "business.sqlite3"
    database = Database(f"sqlite+aiosqlite:///{database_path}")
    app = create_app(
        Settings(
            database_url="",
            api_key="test-business-key",
            simulator_enabled=True,
            auto_create_schema=True,
        ),
        database=database,
    )
    with TestClient(app) as test_client:
        test_client.database_path = database_path
        yield test_client
