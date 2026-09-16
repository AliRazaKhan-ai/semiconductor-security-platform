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

# --- Demonstration ---------------------------------------------------------
# Exam-day sequence:
#   make demo-up      once, before the session
#   make demo-all     background, start it around slide 4
#   make demo-one     live, at slide 11, about two minutes
#   make demo-down    after

.PHONY: demo-up demo-all demo-one demo-watch demo-status demo-down demo-good demo-trojan demo-pair

demo-up:
	./scripts/runtime/start_everything.sh

demo-all:
	@mkdir -p runtime evidence/demo
	@nohup python scripts/demo/run_integrated_demo.py --all --quiet-mint \
		> runtime/demo-all.log 2>&1 & echo $$! > runtime/demo-all.pid
	@echo "Eight chips running in the background, about ten minutes."
	@echo "  make demo-watch    follow progress"
	@echo "  log: runtime/demo-all.log"

demo-one:
	python scripts/demo/run_integrated_demo.py --quiet-mint

demo-watch:
	@tail -f runtime/demo-all.log | grep -vE '"timestamp"|absl|cuda|matplotlib|h5py|urllib3|web3'

demo-status:
	@printf 'fabric peer 7051 : '; ss -ltn | grep -q ':7051' && echo UP || echo DOWN
	@printf 'anvil 8545       : '; ss -ltn | grep -q ':8545' && echo UP || echo DOWN
	@printf 'backend 5000     : '; ss -ltn | grep -q ':5000' && echo UP || echo DOWN
	@printf 'background demo-all: '; \
		[ -f runtime/demo-all.pid ] && kill -0 $$(cat runtime/demo-all.pid) 2>/dev/null \
		&& echo YES || echo NO
	@echo 'dashboard        : http://127.0.0.1:5000/dashboard'

demo-down:
	-@[ -f runtime/demo-all.pid ] && kill $$(cat runtime/demo-all.pid) 2>/dev/null || true
	-@rm -f runtime/demo-all.pid
	./scripts/runtime/stop_everything.sh

demo-good:
	python scripts/demo/run_integrated_demo.py chip_01_good.json --quiet-mint

demo-trojan:
	python scripts/demo/run_integrated_demo.py chip_02_trojan.json --quiet-mint

demo-pair:
	python scripts/demo/run_integrated_demo.py \
		chip_01_good.json chip_02_trojan.json --quiet-mint
