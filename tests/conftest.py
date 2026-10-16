from urllib.parse import urlsplit, urlunsplit

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app


def _test_database_url() -> str:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be set to configure test database")

    parsed = urlsplit(settings.database_url)
    if parsed.path.strip("/") == "task_manager_test":
        raise RuntimeError(
            "DATABASE_URL must point to the application database, not "
            "task_manager_test"
        )

    return urlunsplit(parsed._replace(path="/task_manager_test"))


TEST_DATABASE_URL = _test_database_url()


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def client(session_maker):
    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
def make_user(client):
    async def _make(email: str):
        password = "password123"
        username = f"user-{email.split('@', maxsplit=1)[0]}"
        response = await client.post(
            "/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        assert response.status_code == 201, response.text
        user_id = response.json()["id"]

        response = await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return user_id, headers

    return _make
