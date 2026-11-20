# Analytics Engineering Workshop

Work in progress. This repo is the starter for a 1-day hands-on workshop: JaiDee Mart, a fictional family grocery on a Bangkok soi that delivers across five regions. The stack is dbt Core and DuckDB, on a laptop, with no cloud warehouse.

What is here now:

- a Python generator for the raw shop tables
- a dbt project skeleton that declares those tables as the `jaidee` source and runs a few generic tests

Staging models, intermediate models, marts, and the quality scorecard are not built yet.

Python **3.14** is the version this repo is tested with. 3.15 is the newest stable Python, and it does not work: `dbt-core` 1.12.7 depends on `metricflow`, and the current `metricflow` releases require Python `<3.15`.

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

Install Python 3.14 and make sure the `python3.14` command is on your `PATH`. From the repo root:

```bash
make setup
make check
make data-clean
make build
```

`make check` is the prework check. Each line is `[OK]` or `[FAIL]`. A failure tells you the next command to run.

`make data-clean` writes the extract used by the smoke test. `make build` installs `dbt_utils` and runs `dbt build`. That build passes on the clean extract.

`make data` writes the workshop extract at the same teaching scale. `make build` after `make data` is expected to fail some source tests. Use `make data-clean` when you want the green smoke test again.

Generator tests:

```bash
make test
```

The same steps without Make:

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

dbt does not read `profiles.yml` from the project directory unless `DBT_PROFILES_DIR` points here. The Makefile sets that for its dbt targets. The path inside `profiles.yml` is relative to the `profiles.yml` file.

On Windows, use the dev container in `.devcontainer` (VS Code: Reopen in Container) and then run the same commands. The container image is Python 3.14.

## Data

JaiDee Mart sells in Thai baht. The extract covers 1 April 2025 through 30 September 2026. The default seed is `42`.

| Scale | What it is | Command |
| - | - | - |
| `teaching` | Default. Sized for a laptop dbt build | `make data` or `make data-clean` |
| `large` | Bigger extract for a later compute exercise | `make data-large` |

Add `--clean` for the smoke-test extract. Without it, the generator writes the workshop extract.

The generator writes CSV files under `data/raw/` and loads them into `data/jaidee.duckdb` (schema `raw`). Open the CSVs when you want to look at a row. dbt reads the DuckDB file. Timestamp columns are text, so the clock values in the file are the values that get loaded.

The script prints the row count of each table when it finishes.

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

These files are generated. They are not committed.
