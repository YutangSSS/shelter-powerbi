import pytest

from shelter.db import DATA_DIR, connect


@pytest.fixture(scope="session")
def con():
    if not (DATA_DIR / "aac_intakes.csv").exists():
        pytest.skip("public data not downloaded: run `uv run python scripts/fetch_data.py`")
    return connect()
