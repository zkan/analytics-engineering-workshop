DBT_DIR := jaidee

.PHONY: setup data data-clean data-large build test check app ui require-uv

require-uv:
	@command -v uv >/dev/null 2>&1 || { \
		echo "[FAIL] uv"; \
		echo "       uv is not installed."; \
		echo "       macOS, Linux, or WSL: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "       On Windows, use the dev container or WSL. Plain PowerShell is not supported."; \
		echo "       Then open a new terminal and, from the repo root, run: make setup"; \
		exit 1; \
	}

setup: require-uv
	uv sync --locked
	@echo "Setup complete. Next: make check"

data: require-uv
	uv run --locked python -m generator.generate --seed 42 --scale teaching

data-clean: require-uv
	uv run --locked python -m generator.generate --seed 42 --scale teaching --clean

data-large: require-uv
	uv run --locked python -m generator.generate --seed 42 --scale large

build: require-uv
	@test -f data/jaidee.duckdb || { \
		echo "No data/jaidee.duckdb. Run 'make data-clean' for the smoke test, or 'make data' for the workshop extract."; \
		exit 1; \
	}
	@uv run --locked python -c "import duckdb; c=duckdb.connect('data/jaidee.duckdb', read_only=True); c.execute('select 1 from raw.orders limit 1')" || { \
		echo "data/jaidee.duckdb has no raw.orders table. Run 'make data-clean' or 'make data'."; \
		exit 1; \
	}
	cd $(DBT_DIR) && uv run --locked dbt deps
	cd $(DBT_DIR) && uv run --locked dbt build

test: require-uv
	uv run --locked pytest

check: require-uv
	uv run --locked python scripts/check_prework.py

app: require-uv
	uv run --locked streamlit run app/streamlit_app.py $(STREAMLIT_ARGS)

ui: require-uv
	@test -f data/jaidee.duckdb || { \
		echo "No data/jaidee.duckdb. Run 'make data-clean' for the smoke test, or 'make data' for the workshop extract."; \
		exit 1; \
	}
	uv run --locked python scripts/duckdb_ui.py
