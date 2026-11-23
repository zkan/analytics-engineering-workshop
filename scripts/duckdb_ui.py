#!/usr/bin/env python3
"""Open the DuckDB UI on a read-only copy of the workshop database.

DuckDB allows one writer on a database file, and a read-only opener blocks
that writer too (https://duckdb.org/docs/2.0/connect/concurrency). The UI
process therefore never keeps data/jaidee.duckdb open. It attaches a copy as
jaidee and replaces that copy after the real file is free again, which is
how `dbt build` can run while the notebook stays open.

DuckDB 2.0.1 does not publish the ui extension: INSTALL ui returns HTTP 404
for every platform (duckdb/duckdb#29187). The binaries in vendor/duckdb-ui
are the v2.0.1 builds from duckdb/duckdb-ui commit b19dfd587f
(workflow run 44850194047). They are unsigned, so this process allows
unsigned extensions only when it has to load those files. The page assets
still come from https://ui.duckdb.org. See
https://duckdb.org/docs/2.0/core_extensions/ui.
"""

import gzip
import hashlib
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 4213
VENDOR = ROOT / "vendor" / "duckdb-ui" / "2.0.1"
# gzip sha256, then uncompressed sha256. Platforms follow DuckDB's names.
EXTENSIONS = {
    "linux_amd64": (
        "3c2b84d5eef289a0c52abb298cd211db7919693aa5f8f35bdae6ec091c993607",
        "c5ad530e558de3a3e6819f86bb247a98b72b1f548383eede45396dcc95f8cfb1",
    ),
    "linux_arm64": (
        "9426f0b2de458b5b605061a6570014bfd82880b0ef9c9674b0e7632cc0baf84c",
        "3da31ceae15b1d469b1e0857fd2b41220388448fce1acc70e949969679a50278",
    ),
    "osx_arm64": (
        "fe018a67deaa8a79c2fef38405aea653c6d2cccf74995df195a4faa98aade335",
        "13577bb06eeea04c91948406e28593a0d5e7e848200c3575fc670901aa4c3a09",
    ),
}


class UIError(Exception):
    """A problem the learner can fix, already written as a full message."""


def parse_port(value: str | None = None) -> int:
    raw = os.environ.get("ui_local_port", "") if value is None else value
    raw = raw.strip()
    if not raw:
        return DEFAULT_PORT
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise UIError(
            f"ui_local_port must be a port from 1 to 65535. Got {raw!r}.\n"
            "Example: ui_local_port=4214 make ui"
        )
    return int(raw)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extension_file(platform: str) -> Path:
    if platform not in EXTENSIONS:
        supported = ", ".join(sorted(EXTENSIONS))
        raise UIError(
            f"The DuckDB UI extension in this repo has no build for {platform}.\n"
            f"Included builds: {supported}.\n"
            "DuckDB's UI does not support osx_amd64 (Intel Mac) or windows_arm64.\n"
            "On an Intel Mac or on Windows, use the dev container. Windows can also use WSL."
        )
    gzip_sha, raw_sha = EXTENSIONS[platform]
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cached = cache_root / "jaidee-ui" / "2.0.1" / platform / "ui.duckdb_extension"
    if cached.is_file() and sha256_file(cached) == raw_sha:
        return cached
    packed = VENDOR / f"{platform}.duckdb_extension.gz"
    if not packed.is_file():
        raise UIError(
            f"Missing {packed.relative_to(ROOT)}.\n"
            "Re-clone the repo. The ui extension is part of the project."
        )
    if sha256_file(packed) != gzip_sha:
        raise UIError(
            f"{packed.relative_to(ROOT)} does not match its checksum.\n"
            "Re-clone the repo."
        )
    cached.parent.mkdir(parents=True, exist_ok=True)
    partial = cached.with_suffix(".partial")
    with gzip.open(packed, "rb") as source, partial.open("wb") as target:
        shutil.copyfileobj(source, target)
    if sha256_file(partial) != raw_sha:
        partial.unlink(missing_ok=True)
        raise UIError("The ui extension did not unpack to the expected file.")
    os.replace(partial, cached)
    return cached


def file_signature(path: Path) -> tuple:
    stat = path.stat()
    wal = Path(str(path) + ".wal")
    if wal.exists():
        wal_stat = wal.stat()
        return (stat.st_mtime_ns, stat.st_size, wal_stat.st_mtime_ns, wal_stat.st_size)
    return (stat.st_mtime_ns, stat.st_size, None, None)


def is_lock_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "could not set lock" in text or "conflicting lock" in text


def extension_is_unpublished(exc: BaseException) -> bool:
    text = str(exc)
    return "Failed to download extension" in text and "ui" in text


def copy_database(source: Path, dest: Path) -> tuple:
    """Copy source while a read-only connection holds it, so a writer cannot land mid-copy."""
    probe = duckdb.connect(str(source), read_only=True)
    try:
        signature = file_signature(source)
        partial = dest.with_suffix(".partial")
        shutil.copyfile(source, partial)
        os.replace(partial, dest)
        wal = Path(str(source) + ".wal")
        dest_wal = Path(str(dest) + ".wal")
        if wal.exists():
            partial_wal = Path(str(partial) + ".wal")
            shutil.copyfile(wal, partial_wal)
            os.replace(partial_wal, dest_wal)
        elif dest_wal.exists():
            dest_wal.unlink()
        return signature
    finally:
        probe.close()


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.3):
            return True
    except OSError:
        return False


def port_message(port: int) -> str:
    return (
        f"Port {port} is already in use.\n"
        f"If the DuckDB UI is already running, open http://localhost:{port}\n"
        "To use another port: ui_local_port=4214 make ui\n"
        "The dev container forwards port 4213. Forward any other port yourself."
    )


def lock_message(path: Path) -> str:
    return (
        f"Could not copy {path} because another program has it open.\n"
        "DuckDB allows one writer, and a read-only opener blocks the writer too.\n"
        "Close the other DuckDB shell or wait for dbt to finish, then run make ui again."
    )


def maybe_open_browser(url: str) -> None:
    if os.environ.get("CI") or Path("/.dockerenv").exists():
        return
    if os.environ.get("REMOTE_CONTAINERS") or os.environ.get("CODESPACES"):
        return
    if sys.platform == "darwin":
        command = ["open", url]
    elif sys.platform == "linux" and (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        command = ["xdg-open", url]
    else:
        return
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return


class WorkshopUI:
    def __init__(self, database: Path, port: int | None = None):
        self.database = database
        self.port = DEFAULT_PORT if port is None else port
        self.con: duckdb.DuckDBPyConnection | None = None
        self.loaded_from = ""
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._work: Path | None = None
        self._snapshot: Path | None = None
        self._signature: tuple | None = None
        self._generation = 0

    def __enter__(self) -> "WorkshopUI":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if not self.database.is_file():
            raise UIError(
                f"No {self.database}.\n"
                "From the repo root, run 'make data-clean' for the smoke test, "
                "or 'make data' for the workshop extract."
            )
        self._tmp = tempfile.TemporaryDirectory(prefix="jaidee-ui-")
        self._work = Path(self._tmp.name)
        try:
            self.con = self._open_connection()
            self._set_port()
            self._replace_snapshot(announce=False)
            self._start_server()
        except Exception:
            self.close()
            raise
        url = f"http://localhost:{self.port}"
        print(f"DuckDB UI is at {url}")
        print("The shop data is attached read-only as jaidee. In the notebook, run:")
        print("  USE jaidee;")
        print("  select * from raw.orders limit 10;")
        print("Leave this terminal open. make build in another terminal still works.")
        print("When the build finishes, run the query again.")
        print("Press Ctrl+C to stop.")
        if self.loaded_from == "vendor":
            print("Loaded the ui extension shipped in this repo (DuckDB 2.0.1 has no signed build).")
        maybe_open_browser(url)

    def serve(self) -> None:
        try:
            while True:
                time.sleep(1)
                try:
                    self._replace_snapshot(announce=True)
                except duckdb.Error as exc:
                    if is_lock_error(exc):
                        continue
                    print(f"Could not refresh the copy: {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nDuckDB UI stopped.")

    def refresh(self) -> bool:
        """Copy the workshop database if it changed and attach the new copy."""
        return self._replace_snapshot(announce=False)

    def close(self) -> None:
        if self.con is not None:
            try:
                self.con.execute("CALL stop_ui_server()")
            except duckdb.Error:
                pass
            self.con.close()
            self.con = None
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None
            self._work = None

    def _open_connection(self) -> duckdb.DuckDBPyConnection:
        trial = duckdb.connect()
        platform = trial.execute("select platform from pragma_platform()").fetchone()[0]
        try:
            trial.execute("INSTALL ui")
            trial.execute("LOAD ui")
        except duckdb.Error as exc:
            trial.close()
            if not extension_is_unpublished(exc):
                raise
            path = extension_file(platform)
            connection = duckdb.connect(config={"allow_unsigned_extensions": True})
            connection.execute(f"LOAD {sql_literal(str(path))}")
            self.loaded_from = "vendor"
            return connection
        self.loaded_from = "repository"
        return trial

    def _set_port(self) -> None:
        if port_is_open(self.port):
            raise UIError(port_message(self.port))
        assert self.con is not None
        self.con.execute(f"SET ui_local_port = {int(self.port)}")

    def _start_server(self) -> None:
        assert self.con is not None
        try:
            self.con.execute("CALL start_ui_server()")
        except duckdb.Error as exc:
            if "already started" in str(exc).lower() or port_is_open(self.port):
                raise UIError(port_message(self.port)) from exc
            text = str(exc).lower()
            if "address already in use" in text or "failed to bind" in text or "in use" in text:
                raise UIError(port_message(self.port)) from exc
            raise

    def _replace_snapshot(self, *, announce: bool) -> bool:
        assert self.con is not None and self._work is not None
        if self._snapshot is not None and file_signature(self.database) == self._signature:
            return False
        dest = self._work / f"snapshot-{self._generation}.duckdb"
        try:
            signature = copy_database(self.database, dest)
        except duckdb.Error as exc:
            if is_lock_error(exc):
                if self._snapshot is None:
                    raise UIError(lock_message(self.database)) from exc
                return False
            raise
        # Options follow the alias. DuckDB 2.0 rejects `(READ_ONLY) AS name`.
        verb = "ATTACH OR REPLACE" if self._snapshot is not None else "ATTACH"
        self.con.execute(f"{verb} {sql_literal(str(dest))} AS jaidee (READ_ONLY)")
        self.con.execute("USE jaidee")
        previous = self._snapshot
        self._snapshot = dest
        self._signature = signature
        self._generation += 1
        if previous is not None:
            previous.unlink(missing_ok=True)
            Path(str(previous) + ".wal").unlink(missing_ok=True)
        if announce:
            print("Refreshed jaidee. Run your query again to see the new results.")
        return True


def main() -> int:
    try:
        with WorkshopUI(ROOT / "data" / "jaidee.duckdb", port=parse_port()) as ui:
            ui.serve()
    except UIError as exc:
        print(exc, file=sys.stderr)
        return 1
    except duckdb.Error as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
