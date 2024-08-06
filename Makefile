schema:
	python aijson/scripts/generate_config_schema.py

type:
	pyright aijson

test:
	pytest aijson

test-no-skip:
	pytest --disallow-skip

test-fast:
	pytest -m "not slow" aijson

test-config:
	pytest aijson/tests/test_config.py aijson/tests/static_typing/test_workflow.py

lint:
	ruff check --fix

format:
	ruff format

all: schema format lint type test-fast
