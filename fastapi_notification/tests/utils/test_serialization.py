from datetime import datetime, timedelta, timezone

import pytest

from fastapi_notification.utils.serialization import (
    filter_non_empty_fields,
    generate_title,
)

pytestmark = [pytest.mark.utils, pytest.mark.utils_title_generator]


def test_filter_drops_empty_values() -> None:
    """Empty values are stripped from the representation."""
    data: dict[str, object] = {
        "a": 1,
        "b": None,
        "c": "",
        "d": [],
        "e": {},
        "f": False,
        "g": 0,
    }

    assert filter_non_empty_fields(data) == {"a": 1, "f": False, "g": 0}


def test_filter_drops_excluded_fields() -> None:
    """Named fields are stripped regardless of their value."""
    data = {"username": "ann", "password": "secret"}

    assert filter_non_empty_fields(data, exclude_fields=["password"]) == {
        "username": "ann"
    }


def test_title_combines_description_and_age() -> None:
    """A row with a timestamp is titled with how long ago it happened."""
    timestamp = datetime.now(timezone.utc) - timedelta(hours=2)

    title = generate_title({"description": "ann waved", "timestamp": timestamp})

    assert title == "ann waved 2 hours ago"


def test_title_without_a_timestamp_is_the_description() -> None:
    """A row with no timestamp is titled with its description alone."""
    assert generate_title({"description": "ann waved"}) == "ann waved"


def test_title_requires_a_description() -> None:
    """A row with no description cannot be titled."""
    with pytest.raises(ValueError, match="No description provided"):
        generate_title({"timestamp": datetime.now(timezone.utc)})


def test_title_requires_a_mapping() -> None:
    """Anything that is not a mapping is rejected with a clear message."""
    with pytest.raises(ValueError, match="must be a dictionary"):
        generate_title("not a mapping")  # type: ignore[arg-type]
