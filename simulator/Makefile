.PHONY: lint test run

install:
	uv pip install -e .

lint:
	@status=0; \
	uv run ruff format . || status=1; \
	uv run ruff check . --fix || status=1; \
	uv run ty check . -- --fix || status=1; \
	exit $$status

test: install
	PYTHONPATH=$(PYTHONPATH) uv run -m pytest ./test -vv

run: install
	PYTHONPATH=$(PYTHONPATH) uv run python -m main

benchmark: install
	PYTHONPATH=$(PYTHONPATH) uv run scalene run -- python -m main

benchmark_mem: install
	PYTHONPATH=$(PYTHONPATH) uv run memray run --live -m main

benchmark_view:
	PYTHONPATH=$(PYTHONPATH) uv run scalene view

profile: install
	PYTHONPATH=$(PYTHONPATH) uv run python -m profile_code