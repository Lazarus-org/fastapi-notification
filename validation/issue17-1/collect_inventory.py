"""Record collection and fixture routing; this is not execution evidence."""

import json
from pathlib import Path

import pytest

out = Path(__file__).resolve().parent


class Inventory:
    def pytest_collection_finish(self, session):
        inventory = {
            item.module.__name__ + "." + item.name: {
                "nodeid": item.nodeid,
                "fixtures": item.fixturenames,
                "selected_backend": "engine" in item.fixturenames or "concurrency_store" in item.fixturenames,
            }
            for item in session.items
        }
        previous = json.loads((out.parent / "inventory.json").read_text(encoding="utf-8"))
        missing = sorted(set(previous) - set(inventory))
        assert not missing, missing
        (out / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        summary = {"collected": len(inventory), "previous_cases_retained": len(previous), "missing_previous_cases": missing, "selected_backend_cases": sum(item["selected_backend"] for item in inventory.values())}
        (out / "inventory-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))


raise SystemExit(pytest.main(["fastapi_notification/tests", "--collect-only", "--no-cov", "-q", "-o", "cache_dir=.validation-cache/pytest-inventory"], plugins=[Inventory()]))
