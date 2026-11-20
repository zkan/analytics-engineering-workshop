PYTHON_VERSION := $(shell cat .python-version)
PYTHON ?= python$(PYTHON_VERSION)
VENV := .venv
BIN := $(VENV)/bin

export DBT_PROFILES_DIR := $(abspath .)

.PHONY: setup data data-clean data-large build test check

$(BIN)/python:
	@echo "No virtualenv yet. From the repo root run: make setup"
	@exit 1

setup:
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "Python $(PYTHON_VERSION) is required, and '$(PYTHON)' is not on PATH."; \
		echo "Install Python $(PYTHON_VERSION), then run make setup again."; \
		exit 1; \
	}
	@$(PYTHON) -c "import sys; need=tuple(int(p) for p in '$(PYTHON_VERSION)'.split('.')[:2]); raise SystemExit(0 if sys.version_info[:2]==need else 1)" || { \
		echo "Python $(PYTHON_VERSION) is required."; \
		$(PYTHON) --version; \
		exit 1; \
	}
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -r requirements.txt
	@echo "Setup complete. Next: make check"

data: $(BIN)/python
	$(BIN)/python -m jaidee_mart.generate --seed 42 --scale teaching

data-clean: $(BIN)/python
	$(BIN)/python -m jaidee_mart.generate --seed 42 --scale teaching --clean

data-large: $(BIN)/python
	$(BIN)/python -m jaidee_mart.generate --seed 42 --scale large

build: $(BIN)/python
	@test -f data/jaidee.duckdb || { \
		echo "No data/jaidee.duckdb. Run 'make data-clean' for the smoke test, or 'make data' for the workshop extract."; \
		exit 1; \
	}
	@$(BIN)/python -c "import duckdb; c=duckdb.connect('data/jaidee.duckdb', read_only=True); c.execute('select 1 from raw.orders limit 1')" || { \
		echo "data/jaidee.duckdb has no raw.orders table. Run 'make data-clean' or 'make data'."; \
		exit 1; \
	}
	$(BIN)/dbt deps
	$(BIN)/dbt build

test: $(BIN)/python
	$(BIN)/pytest

check: $(BIN)/python
	$(BIN)/python scripts/check_prework.py
