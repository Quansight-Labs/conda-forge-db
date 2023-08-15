import atexit
import os
from pathlib import Path
from tempfile import TemporaryDirectory


if "CFDB_LOGGING_DIR" not in os.environ:
    tmp = TemporaryDirectory("pytest-logs")
    atexit.register(tmp.cleanup)
    os.environ["CFDB_LOGGING_DIR"] = str(Path(tmp.name, "cfdb.log"))
