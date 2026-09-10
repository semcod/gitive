.PHONY: install test lint cycle dry status clean

install:
	pip install -e ".[dev]"

test:
	pytest -q || python3 tools/offline_test_runner.py

lint:
	ruff check src tests

dry:
	INTUITION_DRY_RUN=true intuition cycle

cycle:
	intuition cycle

status:
	intuition status

clean:
	rm -rf build dist *.egg-info .pytest_cache && find . -name __pycache__ -prune -exec rm -rf {} +
