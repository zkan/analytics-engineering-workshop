import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import duckdb
import pytest

from scripts.duckdb_ui import UIError, WorkshopUI, parse_port


def free_port() -> int:
    family = socket.AF_INET6 if socket.has_ipv6 else socket.AF_INET
    host = "::1" if family == socket.AF_INET6 else "127.0.0.1"
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def tiny_database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute("create schema raw")
    connection.execute("create table raw.orders as select 1 as order_id")
    connection.close()


def test_ui_local_port_rejects_text():
    with pytest.raises(UIError, match="4214"):
        parse_port("nope")


def test_ui_server_answers_and_picks_up_a_later_write(tmp_path):
    database = tmp_path / "jaidee.duckdb"
    tiny_database(database)
    port = free_port()
    ui = WorkshopUI(database, port=port)
    ui.start()
    try:
        # /info is served by the local process. The notebook page is proxied
        # from https://ui.duckdb.org and is not part of this check.
        with urllib.request.urlopen(f"http://localhost:{port}/info", timeout=10) as response:
            assert response.status == 200
            assert response.headers["X-DuckDB-Version"] == "v1.5.6"
        assert ui.con.execute("select order_id from jaidee.raw.orders").fetchall() == [(1,)]

        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import duckdb, sys\n"
                "con = duckdb.connect(sys.argv[1])\n"
                "con.execute('insert into raw.orders values (2)')\n"
                "sys.stdout.write('open\\n')\n"
                "sys.stdout.flush()\n"
                "sys.stdin.readline()\n"
                "con.execute('create table main.learner_model as select 42 as answer')\n"
                "con.close()\n",
                str(database),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert holder.stdout.readline().strip() == "open"
            assert ui.refresh() is False
            with pytest.raises(duckdb.Error, match="Could not set lock"):
                duckdb.connect(str(database)).close()
        finally:
            if holder.poll() is None:
                assert holder.stdin is not None
                holder.stdin.write("\n")
                holder.stdin.flush()
                holder.wait(timeout=10)

        assert ui.refresh() is True
        assert ui.con.execute("select answer from jaidee.main.learner_model").fetchone() == (42,)
        cursor = ui.con.cursor()
        cursor.execute("USE jaidee")
        assert cursor.execute("select answer from main.learner_model").fetchone() == (42,)
    finally:
        ui.close()


def test_second_ui_reports_a_busy_port(tmp_path):
    database = tmp_path / "jaidee.duckdb"
    tiny_database(database)
    port = free_port()
    root = Path(__file__).resolve().parents[1]
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from pathlib import Path\n"
            "from scripts.duckdb_ui import WorkshopUI\n"
            "ui = WorkshopUI(Path(sys.argv[1]), port=int(sys.argv[2]))\n"
            "ui.start()\n"
            "print('READY', flush=True)\n"
            "ui.serve()\n",
            str(database),
            str(port),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 30
        ready = ""
        while time.time() < deadline and child.poll() is None:
            line = child.stdout.readline()
            if line.strip() == "READY":
                ready = line.strip()
                break
        assert ready == "READY", child.stderr.read()
        with pytest.raises(UIError, match="already in use"):
            WorkshopUI(database, port=port).start()
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
