import pytest

from app.config import Settings
from app.database import Database
from app.factory import create_app


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.init_db()
    return database


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "app.db"),
        config_path=str(tmp_path / "missing.yaml"),
        enable_scheduler=False,
        debug=False,
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    return app.test_client()
