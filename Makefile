PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
NPM ?= npm

.PHONY: install api web build-web test eval backtest seed docker

install:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt
	cd web && $(NPM) install

api:
	.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd web && $(NPM) run dev

build-web:
	cd web && $(NPM) run build

test:
	$(PYTHON) -m pytest -q

eval:
	$(PYTHON) evals/run_eval.py

backtest:
	$(PYTHON) evals/run_backtest.py

seed:
	$(PYTHON) scripts/seed.py

docker:
	docker compose up --build
