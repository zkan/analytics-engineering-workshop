#!/usr/bin/env python3
"""Check that this machine can run the JaiDee Mart workshop."""

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "jaidee"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def pins() -> dict[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    found = {}
    for spec in data["project"]["dependencies"] + data["dependency-groups"]["dev"]:
        name, version = spec.split("==", 1)
        found[name] = version
    return found


def expected_python() -> tuple[int, int]:
    text = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    major, minor = (int(part) for part in text.split(".")[:2])
    return major, minor


def tool(name: str) -> str:
    # A venv python is often a symlink. Look beside the symlink first so we
    # find the venv's dbt, not a dbt next to the interpreter it points at.
    candidates = [
        Path(sys.executable).parent / name,
        Path(sys.executable).resolve().parent / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return name


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )


def check_uv() -> int:
    if shutil.which("uv") is None:
        print("[FAIL] uv")
        print("       uv is not installed.")
        print("       macOS, Linux, or WSL: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print("       On Windows, use the dev container or WSL. Plain PowerShell is not supported.")
        print("       Then open a new terminal and, from the repo root, run: make setup")
        return 1
    try:
        version = run(["uv", "--version"])
    except FileNotFoundError:
        version = None
    text = "" if version is None else ANSI.sub("", version.stdout + "\n" + version.stderr).strip()
    match = re.search(r"uv ([0-9][^\s]*)", text)
    if version is not None and version.returncode == 0 and match:
        print(f"[OK]   uv {match.group(1)}")
        return 0
    print("[FAIL] uv")
    print("       uv is installed, but `uv --version` did not run.")
    print("       Reinstall it, then open a new terminal and run: make setup")
    if text:
        print("       " + text.splitlines()[-1])
    return 1


def main() -> int:
    failures = check_uv()
    major, minor = expected_python()
    running = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info[:2] != (major, minor):
        failures += 1
        print(f"[FAIL] Python {running}")
        print(f"       This workshop uses Python {major}.{minor}.")
        print("       From the repo root run: uv python install && make setup")
    else:
        print(f"[OK]   Python {running}")

    versions = pins()
    dbt_bin = tool("dbt")
    expected_core = versions["dbt-core"]
    expected_adapter = versions["dbt-duckdb"]
    try:
        version = run([dbt_bin, "--version"])
    except FileNotFoundError:
        version = None
    version_text = "" if version is None else ANSI.sub("", version.stdout + "\n" + version.stderr)
    core_match = re.search(r"installed:\s*([0-9][^\s]*)", version_text)
    adapter_match = re.search(r"duckdb:\s*([0-9][^\s]*)", version_text)
    core_ok = (
        version is not None
        and version.returncode == 0
        and core_match is not None
        and core_match.group(1) == expected_core
    )
    adapter_ok = (
        version is not None
        and version.returncode == 0
        and adapter_match is not None
        and adapter_match.group(1) == expected_adapter
    )
    if core_ok and adapter_ok:
        print(f"[OK]   dbt-core {expected_core}")
        print(f"[OK]   dbt-duckdb {expected_adapter}")
    else:
        failures += 1
        print("[FAIL] dbt")
        if version is None:
            print("       dbt is not installed for this Python.")
        else:
            found_core = core_match.group(1) if core_match else "not found"
            found_adapter = adapter_match.group(1) if adapter_match else "not found"
            print(f"       Expected dbt-core {expected_core} and dbt-duckdb {expected_adapter}.")
            print(f"       Found dbt-core {found_core} and dbt-duckdb {found_adapter}.")
        print("       From the repo root run: make setup")

    expected_duckdb = versions["duckdb"]
    duckdb_bin = tool("duckdb")
    try:
        duckdb_version = run([duckdb_bin, "--version"])
    except FileNotFoundError:
        duckdb_version = None
    duckdb_text = "" if duckdb_version is None else ANSI.sub("", duckdb_version.stdout + "\n" + duckdb_version.stderr)
    duckdb_match = re.search(r"v?([0-9]+\.[0-9]+\.[0-9]+)", duckdb_text)
    if (
        duckdb_version is not None
        and duckdb_version.returncode == 0
        and duckdb_match is not None
        and duckdb_match.group(1) == expected_duckdb
    ):
        print(f"[OK]   duckdb {duckdb_match.group(1)}")
    else:
        failures += 1
        print("[FAIL] duckdb")
        found_duckdb = duckdb_match.group(1) if duckdb_match else "not found"
        print(f"       Expected the DuckDB CLI v{expected_duckdb}.")
        print(f"       Found {found_duckdb}.")
        print("       From the repo root run: make setup")

    (ROOT / "data").mkdir(exist_ok=True)
    try:
        debug = run([dbt_bin, "debug"], cwd=DBT_DIR)
    except FileNotFoundError:
        debug = None
    debug_text = "" if debug is None else ANSI.sub("", debug.stdout + "\n" + debug.stderr)
    if debug is not None and debug.returncode == 0 and "All checks passed" in debug_text:
        print("[OK]   dbt debug")
    else:
        failures += 1
        print("[FAIL] dbt debug")
        print("       From the repo root run: make setup")
        print("       Then run: make check")
        tail = "\n".join(debug_text.strip().splitlines()[-25:])
        if tail:
            print("       Last lines from dbt debug:")
            for line in tail.splitlines():
                print(f"       {line}")

    print()
    if failures:
        print("Prework check failed. Fix each FAIL line, then run: make check")
        return 1
    print("Prework check passed.")
    print("Next, from the repo root: make data-clean && make build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
