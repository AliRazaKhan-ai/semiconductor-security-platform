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
#   make semi-up      once, before the session
#   make semi-all     background, start it around slide 4
#   make semi-one     live, at slide 11, about two minutes
#   make semi-down    after

.PHONY: semi-incidents semi-incident semi-reset semi-up semi-all semi-one semi-watch semi-status semi-down semi-pair semi-fast semi-help semi-chip001 semi-chip002 semi-chip003 semi-chip004 semi-chip005 semi-chip006 semi-chip007 semi-chip008

semi-up:
	./scripts/runtime/start_everything.sh

semi-all:
	@mkdir -p runtime evidence/demo
	@nohup python scripts/demo/run_integrated_demo.py --all --quiet-mint \
		> runtime/semi-all.log 2>&1 & echo $$! > runtime/semi-all.pid
	@echo "Eight chips running in the background, about ten minutes."
	@echo "  make semi-watch    follow progress"
	@echo "  log: runtime/semi-all.log"

semi-one:
	python scripts/demo/run_integrated_demo.py --quiet-mint

semi-watch:
	@tail -f runtime/semi-all.log | grep -vE '"timestamp"|absl|cuda|matplotlib|h5py|urllib3|web3'

semi-status:
	@printf 'fabric peer 7051 : '; ss -ltn | grep -q ':7051' && echo UP || echo DOWN
	@printf 'anvil 8545       : '; ss -ltn | grep -q ':8545' && echo UP || echo DOWN
	@printf 'backend 5000     : '; ss -ltn | grep -q ':5000' && echo UP || echo DOWN
	@printf 'background semi-all: '; \
		[ -f runtime/semi-all.pid ] && kill -0 $$(cat runtime/semi-all.pid) 2>/dev/null \
		&& echo YES || echo NO
	@echo 'dashboard        : http://127.0.0.1:5000/dashboard'

semi-down:
	-@[ -f runtime/semi-all.pid ] && kill $$(cat runtime/semi-all.pid) 2>/dev/null || true
	-@rm -f runtime/semi-all.pid
	./scripts/runtime/stop_everything.sh

semi-chip001:
	python scripts/demo/run_integrated_demo.py chip_01_good.json --quiet-mint

semi-chip002:
	python scripts/demo/run_integrated_demo.py chip_02_trojan.json --quiet-mint

semi-pair:
	python scripts/demo/run_integrated_demo.py \
		chip_01_good.json chip_02_trojan.json --quiet-mint

semi-chip003:
	python scripts/demo/run_integrated_demo.py chip_03_puf_unstable.json --quiet-mint

semi-chip004:
	python scripts/demo/run_integrated_demo.py chip_04_supplychain_tampered.json --quiet-mint

semi-chip005:
	python scripts/demo/run_integrated_demo.py chip_05_highrisk_supplier.json --quiet-mint

semi-chip006:
	python scripts/demo/run_integrated_demo.py chip_06_counterfeit.json --quiet-mint

semi-chip007:
	python scripts/demo/run_integrated_demo.py chip_07_sanctioned_manufacturer.json --quiet-mint

semi-chip008:
	python scripts/demo/run_integrated_demo.py chip_08_fake_provenance.json --quiet-mint

semi-fast:
	python scripts/demo/run_integrated_demo.py --all --workers 3 --quiet-mint

semi-help:
	@echo 'semi-up        start Docker, Fabric, Anvil, contract, backend'
	@echo 'semi-status    what is running'
	@echo 'semi-chip001   good chip, all eight stages, deploys      ~130s'
	@echo 'semi-chip002   Trojan, stops at hardware security         ~35s'
	@echo 'semi-chip003   weak PUF, stops at authentication          ~35s'
	@echo 'semi-chip004   supply-chain tampered, manual review'
	@echo 'semi-chip005   high-risk supplier, manual review'
	@echo 'semi-chip006   counterfeit, denied and quarantined'
	@echo 'semi-chip007   sanctioned manufacturer, manual review'
	@echo 'semi-chip008   fake provenance, manual review'
	@echo 'semi-pair      chip001 and chip002                       ~165s'
	@echo 'semi-all       all eight, sequential                    ~8.5m'
	@echo 'semi-fast      all eight, three workers                 ~5.5m'
	@echo 'semi-watch     follow a background semi-all'
	@echo 'semi-down      stop everything'

semi-reset:
	@echo "Archiving the current stores, then clearing the dashboard."
	@mkdir -p backups
	@tar czf "backups/stores_$$(date +%Y%m%d-%H%M%S).tar.gz" \
		data/integrated_runs data/event_store data/indexes \
		data/quarantine data/compliance 2>/dev/null || true
	@-./scripts/runtime/stop_backend.sh >/dev/null 2>&1
	@rm -rf data/integrated_runs/* data/event_store/* data/indexes/* \
		data/quarantine/* runtime/semi-all.pid runtime/semi-all.log
	@bash scripts/initialize_event_store.sh >/dev/null 2>&1 || true
	@./scripts/runtime/start_backend.sh
	@echo
	@echo "Dashboard cleared. Archive in backups/."
	@echo "Next: make semi-chip001   (or semi-fast for all eight)"

semi-backup:
	./scripts/maintenance/backup_restore.sh backup

semi-restore-check:
	./scripts/maintenance/backup_restore.sh verify

semi-incidents:
	python scripts/incident.py list

semi-incident:
	@test -n "$(SCAN)" || { echo "usage: make semi-incident SCAN=<scan_id>"; exit 2; }
	python scripts/incident.py open $(SCAN)
