.PHONY: lint test run

PYTHONPATH := $(shell find src -type d | tr '\n' ':')

print_path:
	@echo $(PYTHONPATH)

lint:
	PYTHONPATH=$(PYTHONPATH) uv run ruff check . --fix
	PYTHONPATH=$(PYTHONPATH) uv run ty check . -- --fix

test:
	PYTHONPATH=$(PYTHONPATH) uv run pytest -s ./test

test_log:
	PYTHONPATH=$(PYTHONPATH) uv run pytest -s ./test/test_logger.py

run:
	PYTHONPATH=$(PYTHONPATH) uv run src/main.py

benchmark:
	PYTHONPATH=$(PYTHONPATH) uv run scalene run src/main.py

benchmark_view:
	PYTHONPATH=$(PYTHONPATH) uv run scalene view