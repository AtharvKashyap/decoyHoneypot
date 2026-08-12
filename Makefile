# AI Deception Grid — developer & operator entrypoints.
.PHONY: help venv install test generate demo dash lab lab-down lab-config attack clean

PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

help:
	@echo "Targets:"
	@echo "  install     create venv and install deps"
	@echo "  test        run pytest"
	@echo "  generate    build config/company.yaml + seed docs (AI or offline fallback)"
	@echo "  demo        offline end-to-end: generate -> personas -> attacker -> detect (no Docker)"
	@echo "  dash        run the hub dashboard locally on :8000"
	@echo "  lab         docker compose up the full deception lab"
	@echo "  attack      build + run the live red-team attacker against the lab"
	@echo "  lab-down    tear the lab down"
	@echo "  lab-config  validate docker-compose.yml"
	@echo "  clean       remove data/ and generated seed content"

install: venv
	$(BIN)/pip install -q -r requirements.txt

venv:
	test -d $(VENV) || $(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip

test:
	$(BIN)/pytest

generate:
	$(BIN)/python -m generator.generate

demo:
	$(BIN)/python scripts/run_demo.py

dash:
	$(BIN)/uvicorn hub.app:app --host 0.0.0.0 --port 8000

lab:
	docker compose up --build -d

lab-down:
	docker compose down -v

lab-config:
	docker compose config >/dev/null && echo "docker-compose.yml OK"

# Build the red-team toolbox and run a real kill-chain against the running lab.
# Auto-detects the compose network so it works regardless of project name.
attack:
	docker build -t deception-attacker scripts/live_attack
	docker run --rm --network $$(docker network ls --format '{{.Name}}' | grep deception | head -1) deception-attacker

clean:
	rm -rf data seed/generated
