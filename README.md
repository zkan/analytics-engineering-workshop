# Analytics Engineering Workshop

This repo is the starter for a 1-day hands-on workshop. It is still a work in progress.

The workshop is built around JaiDee Mart, a fictional family grocery store on a Bangkok soi (side street) that delivers across five regions. You will use two tools: dbt Core, which turns SQL files into tested tables, and DuckDB, a small database that runs on your laptop. Everything runs locally, with no cloud data warehouse.

## What is here so far

- A Python generator that creates the raw shop tables.
- A dbt project skeleton, in the `jaidee` folder. It declares those tables as the `jaidee` source and runs a few generic tests on them.

Not built yet: the staging models, intermediate models, marts, and the quality scorecard.

## Words used in this README

- **Extract**: a snapshot of the shop's raw data, as the generator writes it.
- **dbt source**: dbt's name for raw tables that come from outside dbt. Here, the source is called `jaidee`.
- **Generic test**: a ready-made dbt check that you attach to a column or table.
- **Smoke test**: a quick run that shows the setup works from end to end.
- **Virtual environment** (venv, or virtualenv): a private folder of Python packages for this project only, so it does not clash with anything else on your laptop.
- **Lockfile**: a file that records the exact version of every package, so every install gets the same ones.
- **uv**: a program that installs this project's Python packages, and Python itself when needed. It uses a lockfile, so everyone gets the same versions.
- **`PATH`**: the list of folders your terminal searches when you type a command.
- **Make**: a tool that runs the shortcut commands defined in `Makefile`, such as `make setup`.
- **Dev container**: a ready-made Linux environment that VS Code runs for you, with Python already installed.
- **Seed**: a starting number for the random data. The same seed gives everyone the same data.
- **Grain**: what one row in a table stands for.

## Which Python version

This repo is tested with Python **3.14**. Python 3.15 is the newest stable release, but it does not work here: `dbt-core` 1.12.7 depends on `metricflow`, and the current `metricflow` releases require Python `<3.15`.

## Files and folders

| Name | Description |
| - | - |
| `.devcontainer/devcontainer.json` | Dev container definition. Python 3.14. On create, installs uv and runs `uv sync --locked` |
| `.github/workflows/ci.yml` | GitHub Actions workflow. Installs uv 0.13.9, runs `uv sync --locked`, runs pytest, generates the clean extract, then `dbt deps` and `dbt build` |
| `.gitignore` | Ignores the virtualenv, dbt build folders, and generated data |
| `.python-version` | Python version uv uses for this project. The prework check reads it too |
| `jaidee/` | The dbt project. Holds `dbt_project.yml`, `profiles.yml` (local DuckDB, no secrets), and `models/staging/_sources.yml` |
| `jaidee_mart/` | Generator package. Run it with `python -m jaidee_mart.generate` |
| `scripts/check_prework.py` | Prints OK or FAIL for uv, the Python version, the dbt version, and `dbt debug` |
| `tests/` | pytest tests for the generator |
| `pytest.ini` | Puts the repo root on the pytest import path |
| `pyproject.toml` | Names the Python version and the pinned packages. pytest is in the dev group |
| `uv.lock` | Lockfile written by uv. `uv sync --locked` installs these exact packages |
| `Makefile` | Setup, generate, dbt build, pytest, and the prework check |
| `LICENSE` | MIT license |
| `README.md` | This file |

## Getting started

First, install uv. This repo was checked with uv 0.13.9. If you do not have Python 3.14 yet, uv downloads it for you.

On macOS, Linux, or WSL:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, see [On Windows](#on-windows) first.

After the install, close your terminal and open a new one, so `uv` is on your `PATH`. In the new terminal, go to the repo root (the top folder of this repo) and run:

```bash
make setup
make check
make data-clean
make build
```

`make setup` runs `uv sync --locked`. That creates the `.venv` folder and installs the locked packages. `--locked` means "use `uv.lock` as it is committed, and stop if it does not match."

`make check` is the prework check. It confirms your laptop is ready. Each line says `[OK]` or `[FAIL]`, and a failure tells you which command to run next.

`make data-clean` writes the clean extract that the smoke test uses. `make build` runs `dbt deps` and `dbt build` from inside the `jaidee` folder. On the clean extract, that build passes.

### Clean extract or workshop extract

`make data` writes the workshop extract, at the same teaching scale. If you run `make build` after `make data`, some source tests are expected to fail. To get the passing smoke test back, run `make data-clean`.

### Run the generator tests

```bash
make test
```

### Without Make

If you do not have Make, run the same steps by hand, starting from the repo root:

- `uv sync` creates `.venv`.
- The `source` line turns that virtual environment on, so the `dbt` command is available.
- `cd jaidee` moves you into the dbt project folder before the dbt commands. dbt reads `profiles.yml` in that folder, so you do not need to set `DBT_PROFILES_DIR`.

```bash
uv sync --locked
uv run python scripts/check_prework.py
uv run python -m jaidee_mart.generate --seed 42 --scale teaching --clean
source .venv/bin/activate
cd jaidee
dbt deps
dbt build
```

You can also use `uv run` from inside `jaidee`. It finds the `pyproject.toml` and `.venv` in the repo root. For example: `cd jaidee && uv run dbt build`.

### On Windows

On Windows, use the dev container or WSL. Plain PowerShell is not supported, because `make` and `source .venv/bin/activate` do not work there.

- **Dev container**: open the repo in VS Code and choose Reopen in Container (the setup is in `.devcontainer`). The container is Linux, installs uv when it is created, and uses Python 3.14. Run every command in this README in the container's terminal.
- **WSL** (Windows Subsystem for Linux): open a WSL terminal, clone the repo inside WSL, and follow the macOS and Linux steps above.

## Data

JaiDee Mart sells in Thai baht. The extract covers 1 April 2025 through 30 September 2026. The default seed is `42`.

| Scale | What it is | Command |
| - | - | - |
| `teaching` | Default. Sized for a laptop dbt build | `make data` or `make data-clean` |
| `large` | Bigger extract for a later compute exercise | `make data-large` |

Add `--clean` to the generator command to get the smoke-test extract. Without it, the generator writes the workshop extract.

The generator writes CSV files under `data/raw/` and loads them into `data/jaidee.duckdb`, in the `raw` schema (a named group of tables inside the database). The `data` folder sits at the repo root, so from inside `jaidee`, dbt opens the file as `../data/jaidee.duckdb`. Open the CSVs when you want to look at a single row. dbt reads the DuckDB file, not the CSVs. Timestamp columns are stored as text, so the clock values in the file are exactly the values that get loaded.

When the script finishes, it prints the row count of each table.

Each table and its grain:

| Table | Grain |
| - | - |
| `customers` | One signup. `region` is Bangkok, Central, North, Northeast, or South. `channel` is line, web, facebook, phone, or walk_in |
| `stores` | One store |
| `products` | One product. `unit_price_thb` and `unit_cost_thb` are baht |
| `orders` | One order header. `subtotal_thb`, `discount_thb`, `tax_thb` (7% VAT), `delivery_fee_thb`, and `order_total_thb` are baht. `order_placed_at` is when the order was placed. `recorded_at` is when the row landed |
| `order_items` | One line on an order |
| `deliveries` | One delivery attempt. `delivered_at` is empty when the order has not arrived |
| `payments` | One payment event. `status` is succeeded, failed, or refunded. `amount_thb` is baht |
| `reviews` | One score, from 1 to 5, after an order |

These files are generated on your laptop. They are not committed to the repo.
