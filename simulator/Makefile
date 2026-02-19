.PHONY:	lint test run

lint:
	uv run ruff check . --fix
	uv run ty check . -- --fix

test:
	uv run pytest ./test

run:
	uv run src/main.py