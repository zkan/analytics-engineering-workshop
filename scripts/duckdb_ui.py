#!/usr/bin/env python3
"""Open the DuckDB UI on a read-only copy of the workshop database.

DuckDB allows one writer on a database file, and a read-only opener blocks
that writer too (https://duckdb.org/docs/1.5/connect/concurrency). The UI
process therefore never keeps data/jaidee.duckdb open. It attaches a copy as
jaidee and replaces that copy after the real file is free again, which is
how `dbt build` can run while the notebook stays open.

The ui extension is the signed build published for DuckDB 1.5.6. The first
start downloads it. The page assets still come from https://ui.duckdb.org.
See https://duckdb.org/docs/1.5/core_extensions/ui.
"""

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
        connection = duckdb.connect()
        try:
            connection.execute("INSTALL ui")
            connection.execute("LOAD ui")
        except duckdb.Error as exc:
            connection.close()
            raise UIError(
                "Could not install the DuckDB ui extension.\n"
                "The first run downloads it, so this needs internet.\n"
                "Check your connection and run make ui again.\n"
                f"{exc}"
            ) from exc
        return connection

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
        # DuckDB 1.5: ATTACH 'file' AS name (READ_ONLY). Options follow the alias.
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
