DBT_DIR := jaidee
export DBT_PROFILES_DIR := $(abspath $(DBT_DIR))

.PHONY: setup data data-clean data-large build test check require-uv

require-uv:
	@command -v uv >/dev/null 2>&1 || { \
		echo "[FAIL] uv"; \
		echo "       uv is not installed."; \
		echo "       macOS and Linux: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "       Windows (PowerShell): powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""; \
		echo "       Then open a new terminal and, from the repo root, run: make setup"; \
		exit 1; \
	}

setup: require-uv
	uv sync --locked
	@echo "Setup complete. Next: make check"

data: require-uv
	uv run --locked python -m jaidee_mart.generate --seed 42 --scale teaching

data-clean: require-uv
	uv run --locked python -m jaidee_mart.generate --seed 42 --scale teaching --clean

data-large: require-uv
	uv run --locked python -m jaidee_mart.generate --seed 42 --scale large

build: require-uv
	@test -f data/jaidee.duckdb || { \
		echo "No data/jaidee.duckdb. Run 'make data-clean' for the smoke test, or 'make data' for the workshop extract."; \
		exit 1; \
	}
	@uv run --locked python -c "import duckdb; c=duckdb.connect('data/jaidee.duckdb', read_only=True); c.execute('select 1 from raw.orders limit 1')" || { \
		echo "data/jaidee.duckdb has no raw.orders table. Run 'make data-clean' or 'make data'."; \
		exit 1; \
	}
	uv run --locked dbt deps --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)
	uv run --locked dbt build --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

test: require-uv
	uv run --locked pytest

check: require-uv
	uv run --locked python scripts/check_prework.py
