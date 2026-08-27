# Atajos de desarrollo. `make ayuda` lista los objetivos.
.DEFAULT_GOAL := ayuda
SHELL := /bin/bash

VENV      := .venv
VENV_SAM  := .venv-sam
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
SAM       := $(VENV_SAM)/bin/sam
STACK     ?= cloud-flashcards
REGION    ?= us-east-1

# node suele venir de nvm, que no exporta su PATH a shells no interactivos.
NODE_BIN := $(shell dirname $$(command -v node 2>/dev/null) 2>/dev/null || ls -d $$HOME/.nvm/versions/node/*/bin 2>/dev/null | tail -1)
NPM      := PATH="$(NODE_BIN):$$PATH" npm

export SAM_CLI_TELEMETRY = 0

.PHONY: ayuda entorno test test-backend test-frontend test-e2e lint validate build deploy seed dev limpiar

ayuda:
	@grep -E '^[a-z0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

entorno: ## Crea ambos venv, instala dependencias de Python y de Node
	python3 -m venv $(VENV) && $(PIP) install -q -r requirements-dev.txt
	python3 -m venv $(VENV_SAM) && $(VENV_SAM)/bin/pip install -q aws-sam-cli
	cd frontend && $(NPM) install --no-audit --no-fund

test: test-backend test-frontend ## Ejecuta toda la bateria de tests

test-backend: ## pytest + moto (AWS simulado, sin credenciales reales)
	$(PY) -m pytest tests/ -v

test-frontend: ## Vitest + Testing Library sobre el componente
	cd frontend && $(NPM) test

test-e2e: ## Playwright en navegador real contra el API desplegado en AWS
	cd frontend && $(NPM) run test:e2e

lint: ## cfn-lint sobre la plantilla
	$(VENV)/bin/cfn-lint template.yaml && echo "cfn-lint OK"

validate: ## sam validate --lint
	$(SAM) validate --lint --region $(REGION)

build: ## sam build dentro del contenedor python3.12 (requiere Docker)
	$(SAM) build --use-container

deploy: build ## Despliegue guiado interactivo
	$(SAM) deploy --guided --stack-name $(STACK) --region $(REGION)

seed: ## Sube todos los mazos de ejemplo, conservando las carpetas de tematica
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
	  --query "Stacks[0].Outputs[?OutputKey=='DecksBucketName'].OutputValue" --output text); \
	echo "Subiendo a s3://$$BUCKET/"; \
	aws s3 sync sample-decks/ s3://$$BUCKET/ --exclude "*" --include "*.md" --region $(REGION)

dev: ## Servidor de desarrollo del frontend
	cd frontend && $(NPM) run dev

limpiar: ## Borra artefactos de build y caches
	rm -rf .aws-sam frontend/dist .pytest_cache frontend/e2e/.artifacts
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
