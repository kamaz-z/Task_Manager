import pytest


@pytest.mark.asyncio
async def test_register_and_duplicate(client):
    data = {
        "username": "alice",
        "email": "a@test.com",
        "password": "password123",
    }

    response = await client.post("/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["username"] == "alice"
    assert "password" not in response.json()
    assert "hashed_password" not in response.json()

    response = await client.post("/auth/register", json=data)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "a@test.com",
            "password": "password123",
        },
    )

    response = await client.post(
        "/auth/login",
        data={"username": "a@test.com", "password": "wrong-pass"},
    )
    assert response.status_code == 401
