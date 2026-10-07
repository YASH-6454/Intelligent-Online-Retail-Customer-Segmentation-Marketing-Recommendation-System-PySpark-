import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spark_session import get_spark  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    s = get_spark("tests", "local[2]", {"spark.sql.shuffle.partitions": "2", "spark.driver.memory": "1g"})
    yield s
    s.stop()
