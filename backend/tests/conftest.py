import os, sys, tempfile
from pathlib import Path

# Isolated DB + data dir for the whole test run; no network, no LLM.
_tmp = tempfile.mkdtemp(prefix="finn_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["LLM_PROVIDER"] = "none"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
