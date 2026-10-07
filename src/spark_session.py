"""Single place that builds the SparkSession used by every stage."""
import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

from src import config

_BREW_JDK21 = Path("/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home")


def _ensure_java() -> None:
    """Spark 4 is tested on LTS JDKs (17/21); prefer Homebrew's openjdk@21 if JAVA_HOME is unset."""
    if not os.environ.get("JAVA_HOME") and _BREW_JDK21.exists():
        os.environ["JAVA_HOME"] = str(_BREW_JDK21)
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def get_spark(app_name: str = config.SPARK_APP_NAME, master: str = config.SPARK_MASTER,
              extra_conf: dict | None = None) -> SparkSession:
    _ensure_java()
    builder = SparkSession.builder.appName(app_name).master(master)
    for key, value in {**config.SPARK_CONF, **(extra_conf or {})}.items():
        builder = builder.config(key, value)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
