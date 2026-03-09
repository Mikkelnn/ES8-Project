.PHONY: lint test run

# PYTHONPATH := $(shell find src -type d | tr '\n' ':')

install:
	uv pip install -e .

print_path:
	@echo $(PYTHONPATH)

lint:
	PYTHONPATH=$(PYTHONPATH) uv run ruff check . --fix
	PYTHONPATH=$(PYTHONPATH) uv run ty check . -- --fix

test: install
	PYTHONPATH=$(PYTHONPATH) uv run pytest ./test

run: install
	PYTHONPATH=$(PYTHONPATH) uv run python -m main

benchmark:
	PYTHONPATH=$(PYTHONPATH) uv run scalene run main

benchmark_view:
	PYTHONPATH=$(PYTHONPATH) uv run scalene view

profile: install
	PYTHONPATH=$(PYTHONPATH) uv run python -m profile_code