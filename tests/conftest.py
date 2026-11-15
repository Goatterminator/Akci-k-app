import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Minden teszt saját, üres SQLite adatbázist kap."""
    from app import config, db

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


@pytest.fixture()
def client(fresh_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config

    monkeypatch.setattr(config, "AUTO_REFRESH", False)
    from app.main import app

    with TestClient(app) as c:
        yield c


def load(name: str):
    import json

    path = FIXTURES / name
    if name.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


os.environ.setdefault("AUTO_REFRESH", "0")
