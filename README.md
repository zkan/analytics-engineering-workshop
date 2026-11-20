# Analytics Engineering Workshop

This repo is the starter for a 1-day hands-on workshop. It is still a work in progress.

The workshop is built around JaiDee Mart, a fictional family grocery store on a Bangkok soi (side street) that delivers across five regions. You will use two tools: dbt Core, which turns SQL files into tested tables, and DuckDB, a small database that runs on your laptop. Everything runs locally, with no cloud data warehouse.

## What is here so far

- A Python generator that creates the raw shop tables.
- A dbt project skeleton. It declares those tables as the `jaidee` source and runs a few generic tests on them.

Not built yet: the staging models, intermediate models, marts, and the quality scorecard.

## Words used in this README

- **Extract**: a snapshot of the shop's raw data, as the generator writes it.
- **dbt source**: dbt's name for raw tables that come from outside dbt. Here, the source is called `jaidee`.
- **Generic test**: a ready-made dbt check that you attach to a column or table.
- **Smoke test**: a quick run that shows the setup works from end to end.
- **Virtual environment** (venv, or virtualenv): a private folder of Python packages for this project only, so it does not clash with anything else on your laptop.
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
| `.devcontainer/devcontainer.json` | Dev container definition. Python 3.14, then `pip install -r requirements.txt` |
| `.github/workflows/ci.yml` | GitHub Actions workflow. Installs the pinned packages, runs pytest, generates the clean extract, then `dbt deps` and `dbt build` |
| `.gitignore` | Ignores the virtualenv, dbt build folders, and generated data |
| `.python-version` | Python version used by `make setup` and the prework check |
| `jaidee_mart/` | Generator package. Run it with `python -m jaidee_mart.generate` |
| `models/staging/_sources.yml` | dbt source `jaidee` for the eight raw tables, plus a few generic tests |
| `scripts/check_prework.py` | Prints OK or FAIL for the Python version, the dbt version, and `dbt debug` |
| `tests/` | pytest tests for the generator |
| `dbt_project.yml` | dbt project file |
| `packages.yml` | Pins `dbt_utils` |
| `package-lock.yml` | Lockfile written by `dbt deps` |
| `profiles.yml` | Local DuckDB profile. No secrets. The database path is `data/jaidee.duckdb` |
| `pytest.ini` | Puts the repo root on the pytest import path |
| `requirements.txt` | Pinned Python packages |
| `Makefile` | Setup, generate, dbt build, pytest, and the prework check |
| `LICENSE` | MIT license |
| `README.md` | This file |

## Getting started

Install Python 3.14 and make sure the `python3.14` command is on your `PATH`. Then open a terminal in the repo root (the top folder of this repo) and run:

```bash
make setup
make check
make data-clean
make build
```

`make check` is the prework check. It confirms your laptop is ready. Each line says `[OK]` or `[FAIL]`, and a failure tells you which command to run next.

`make data-clean` writes the clean extract that the smoke test uses. `make build` installs `dbt_utils` and runs `dbt build`. On the clean extract, that build passes.

### Clean extract or workshop extract

`make data` writes the workshop extract, at the same teaching scale. If you run `make build` after `make data`, some source tests are expected to fail. To get the passing smoke test back, run `make data-clean`.

### Run the generator tests

```bash
make test
```

### Without Make

If you do not have Make, run the same steps by hand. The first three lines create a virtual environment in `.venv`, turn it on, and install the pinned packages.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DBT_PROFILES_DIR=.
python scripts/check_prework.py
python -m jaidee_mart.generate --seed 42 --scale teaching --clean
dbt deps
dbt build
```

dbt does not read `profiles.yml` (the file that tells dbt how to connect to the database) from the project folder unless `DBT_PROFILES_DIR` points here. The `export DBT_PROFILES_DIR=.` line does that, and the Makefile sets it for its own dbt targets. The path inside `profiles.yml` is relative to the `profiles.yml` file itself.

### On Windows

Use the dev container in `.devcontainer` (in VS Code: Reopen in Container), then run the same commands inside it. The container image uses Python 3.14.

## Data

JaiDee Mart sells in Thai baht. The extract covers 1 April 2025 through 30 September 2026. The default seed is `42`.

| Scale | What it is | Command |
| - | - | - |
| `teaching` | Default. Sized for a laptop dbt build | `make data` or `make data-clean` |
| `large` | Bigger extract for a later compute exercise | `make data-large` |

Add `--clean` to the generator command to get the smoke-test extract. Without it, the generator writes the workshop extract.

The generator writes CSV files under `data/raw/` and loads them into `data/jaidee.duckdb`, in the `raw` schema (a named group of tables inside the database). Open the CSVs when you want to look at a single row. dbt reads the DuckDB file, not the CSVs. Timestamp columns are stored as text, so the clock values in the file are exactly the values that get loaded.

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
