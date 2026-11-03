"""Record fixture-based test grouping; collection is not execution evidence."""
import json
from pathlib import Path


def pytest_collection_finish(session):
    inventory = {
        item.module.__name__ + "." + item.name: {
            "nodeid": item.nodeid, "fixtures": item.fixturenames
        }
        for item in session.items
    }
    Path("validation/inventory.json").write_text(json.dumps(inventory, indent=2))
