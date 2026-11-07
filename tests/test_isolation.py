"""The tests keep away from the user's real folders, even a test that undoes the isolation (conftest): made-up invoices
went into the user's real records.db that way, twice. Run in a pytest of its own, told that a made-up folder is the
real one, so nothing here can reach the real one."""
import os
import subprocess
import sys
from pathlib import Path

INNER = """
import os

def test_it(monkeypatch):
    monkeypatch.undo()
    print("APPDATA=" + os.environ["APPDATA"])
    print("USERPROFILE=" + os.environ["USERPROFILE"])
    print("HOME=" + os.environ["HOME"])
"""


def test_a_test_undoing_the_isolation_still_cannot_reach_the_real_folders(tmp_path):
    """monkeypatch.undo() puts back what was there before the test: the run's temporary folder, not the real one. The
    test is failed for it all the same."""
    real = str(tmp_path / "the real folders")
    (tmp_path / "test_inner.py").write_text(INNER, encoding="utf-8")
    tests = Path(__file__).parent
    env = {**os.environ, "APPDATA": real, "USERPROFILE": real, "HOME": real,
           "PYTHONPATH": os.pathsep.join((str(tests), str(tests.parent)))}
    out = subprocess.run([sys.executable, "-B", "-m", "pytest", "test_inner.py", "-s", "-q", "-p", "conftest",
                          "-p", "no:cacheprovider", "--rootdir", str(tmp_path), "-c", os.devnull],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    text = out.stdout + out.stderr
    seen = dict(line.split("=", 1) for line in text.splitlines()
                if line.split("=", 1)[0].lstrip(".F") in ("APPDATA", "USERPROFILE", "HOME"))
    assert len(seen) == 3, text
    for folder in seen.values():
        assert "the real folders" not in folder and "yinit-tests-" in folder
    assert "undid the isolation" in text and out.returncode != 0
