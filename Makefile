.PHONY: test test-e2e

test:
	uv run pytest tests/unit/ -v

test-e2e:
	uv run pytest tests/e2e/ -v -m e2e
