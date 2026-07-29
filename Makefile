PYTHON ?= python

.PHONY: install test test-fast lint typecheck compile run health clean

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

test-fast:
	$(PYTHON) -m pytest tests/api tests/dashboard tests/pipeline -q

lint:
	ruff check app tests terminal

typecheck:
	mypy app

compile:
	$(PYTHON) -m compileall -q app terminal
	$(PYTHON) -m py_compile manage.py

run:
	./scripts/runtime/start_backend.sh

health:
	curl -fsS http://localhost:5000/health/ready | $(PYTHON) -m json.tool

clean:
	find app terminal tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
