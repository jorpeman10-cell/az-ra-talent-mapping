# tests/conftest.py
# Single env-injection point for the whole test dir. pytest imports conftest
# BEFORE any test module, so api.main/store see these paths deterministically.
# No test module may set these env vars itself.
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["HEADHUNT_DATA_DIR"] = TMP
os.environ["HEADHUNT_CONFIG_DIR"] = os.path.join(TMP, "config")
