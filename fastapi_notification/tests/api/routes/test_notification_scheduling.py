"""HTTP runtime contracts for user-isolated scheduling settings."""

from typing import Any

import pytest

pytestmark = [pytest.mark.api, pytest.mark.api_routes]


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "quiet-hours",
            {
                "start_time": "22:00:00",
                "end_time": "07:00:00",
                "timezone": "Asia/Tehran",
            },
        ),
        ("digest-schedules", {"local_time": "09:00:00", "timezone": "Europe/Berlin"}),
    ],
)
async def test_scheduling_crud_is_authenticated_and_user_isolated(
    client: Any, as_user: Any, user: Any, other_user: Any, path: Any, payload: Any
) -> None:
    url = f"/notifications/{path}/"
    assert (await client.get(url)).status_code == 401
    assert (await client.put(url, json=payload)).status_code == 401
    as_user(user)
    response = await client.put(url, json=payload)
    assert response.status_code == 200
    row = response.json()
    assert row["user_id"] == str(user.id)
    assert row["timezone"] == payload["timezone"]
    assert (await client.get(url)).json()["results"] == [row]
    as_user(other_user)
    assert (await client.get(url)).json()["results"] == []
    assert (await client.delete(url)).status_code == 204
    as_user(user)
    assert len((await client.get(url)).json()["results"]) == 1
    assert (await client.delete(url)).status_code == 204
    assert (await client.get(url)).json()["results"] == []


@pytest.mark.parametrize(
    "path,payload",
    [
        ("quiet-hours", {"start_time": "22:00:00Z", "end_time": "07:00:00"}),
        (
            "quiet-hours",
            {
                "start_time": "22:00:00",
                "end_time": "07:00:00",
                "timezone": "Mars/Olympus",
            },
        ),
        ("digest-schedules", {"local_time": "09:00:00", "frequency": "monthly"}),
        ("digest-schedules", {"local_time": "09:00:00Z"}),
        ("digest-schedules", {"local_time": "09:00:00", "weekday": 0}),
    ],
)
async def test_scheduling_invalid_requests_return_422(
    client: Any, as_user: Any, user: Any, path: Any, payload: Any
) -> None:
    as_user(user)
    assert (
        await client.put(f"/notifications/{path}/", json=payload)
    ).status_code == 422


def test_openapi_registers_scheduling_without_get_mutations(app_factory: Any) -> None:
    schema = app_factory().openapi()
    for path in ["quiet-hours", "digest-schedules"]:
        operations = schema["paths"][f"/notifications/{path}/"]
        assert set(operations) == {"get", "put", "delete"}
    for path, operations in schema["paths"].items():
        if any(
            action in path
            for action in ["mark_as_seen", "mark_as_unseen", "clear_notification"]
        ):
            assert "get" not in operations
