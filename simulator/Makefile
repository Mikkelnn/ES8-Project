.PHONY:	lint test run

lint:
	uv run ruff check . --fix
	uv run ty check . -- --fix

test:
	uv run pytest ./test

run:
	uv run src/main.py

benchmark:
	uv run scalene run src/main.py

benchmark_view:
	uv run scalene view