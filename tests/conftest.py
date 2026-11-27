import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["KEITARO_URL"] = "https://kt.test"
os.environ["KEITARO_API_KEY"] = "test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import campaigns  # noqa: E402

API = "https://kt.test/admin_api/v1"


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    campaigns.reset_offers_cache()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
