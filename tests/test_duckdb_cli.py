import subprocess
import sys
from pathlib import Path

DUCKDB = Path(sys.executable).parent / "duckdb"


def test_duckdb_cli_is_pinned_and_ui_extension_installs():
    assert DUCKDB.is_file()
    version = subprocess.run(
        [str(DUCKDB), "--version"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "v1.5.6" in version.stdout + version.stderr
    installed = subprocess.run(
        [str(DUCKDB), "-c", "INSTALL ui; LOAD ui;"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert installed.returncode == 0
