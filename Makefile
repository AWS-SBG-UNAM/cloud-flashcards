# Atajos de desarrollo. `make ayuda` lista los objetivos.
.DEFAULT_GOAL := ayuda
SHELL := /bin/bash

VENV      := .venv
VENV_SAM  := .venv-sam
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
SAM       := $(VENV_SAM)/bin/sam
STACK           ?= cloud-flashcards
REGION          ?= mx-central-1
STAGE           ?= dev
STACK_FRONTEND  ?= cloud-flashcards-frontend
REGION_FRONTEND ?= us-east-1

# node suele venir de nvm, que no exporta su PATH a shells no interactivos.
NODE_BIN := $(shell dirname $$(command -v node 2>/dev/null) 2>/dev/null || ls -d $$HOME/.nvm/versions/node/*/bin 2>/dev/null | tail -1)
NPM      := PATH="$(NODE_BIN):$$PATH" npm

export SAM_CLI_TELEMETRY = 0

.PHONY: ayuda entorno test test-backend test-frontend test-e2e lint validate build deploy seed dev clean amplify-deploy amplify-url

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

build: ## sam build local, alineado al runtime python3.14 (sin Docker)
	$(SAM) build

deploy: build ## Despliegue guiado interactivo
	$(SAM) deploy --guided --stack-name $(STACK) --region $(REGION)

seed: ## Sube los mazos locales, conservando las carpetas de tematica
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
	  --query "Stacks[0].Outputs[?OutputKey=='DecksBucketName'].OutputValue" --output text); \
	COUNT=$$(find sample-decks -name '*.md' -not -path '*/_notion/*' 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$COUNT" -gt 0 ]; then \
	  echo "Subiendo $$COUNT mazo(s) de sample-decks/ a s3://$$BUCKET/"; \
	  aws s3 sync sample-decks/ s3://$$BUCKET/ --exclude "*" --include "*.md" \
	    --exclude "_notion/*" --region $(REGION); \
	else \
	  echo "sample-decks/ esta vacio (la carpeta no se versiona)."; \
	  echo "Subiendo el fixture de tests como mazo inicial para que el catalogo no salga vacio."; \
	  aws s3 cp tests/fixtures/mazo-canonico.md \
	    "s3://$$BUCKET/General/fundamentos-de-aws.md" --region $(REGION); \
	fi

dev: ## Servidor de desarrollo del frontend
	cd frontend && $(NPM) run dev

amplify-deploy: ## Crea/actualiza el stack de Amplify Hosting (frontend) en us-east-1
	@test -n "$(API_BASE_URL)" || (echo "Falta API_BASE_URL (output ApiBaseUrl del stack de backend)"; exit 1)
	@test -n "$(GITHUB_ACCESS_TOKEN)" || (echo "Falta GITHUB_ACCESS_TOKEN (token de GitHub, ver README)"; exit 1)
	@aws cloudformation deploy \
	  --template-file amplify.template.yaml \
	  --stack-name $(STACK_FRONTEND) \
	  --region $(REGION_FRONTEND) \
	  --parameter-overrides ApiBaseUrl=$(API_BASE_URL) AccessToken=$(GITHUB_ACCESS_TOKEN)

amplify-url: ## Imprime la URL de la rama publicada en Amplify
	@aws cloudformation describe-stacks --stack-name $(STACK_FRONTEND) --region $(REGION_FRONTEND) \
	  --query "Stacks[0].Outputs[?OutputKey=='BranchUrl'].OutputValue" --output text

clean: ## Borra artefactos locales, vacia los buckets y elimina el stack de AWS
	rm -rf .aws-sam frontend/dist .pytest_cache frontend/e2e/.artifacts
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
	  --query "Stacks[0].Outputs[?OutputKey=='DecksBucketName'].OutputValue" --output text 2>/dev/null); \
	if [ -n "$$BUCKET" ] && [ "$$BUCKET" != "None" ]; then \
	  echo "Desconectando notificaciones de s3://$$BUCKET/"; \
	  echo "(si no, borrar sus objetos reinvoca ParserFunction, que recrea su" ; \
	  echo " log group fuera del control de CloudFormation y rompe el proximo deploy)"; \
	  aws s3api put-bucket-notification-configuration --bucket "$$BUCKET" \
	    --notification-configuration '{}' --region $(REGION); \
	  echo "Vaciando s3://$$BUCKET/ (tiene versionado: se purgan versiones y delete markers)"; \
	  TMP=$$(mktemp); \
	  aws s3api list-object-versions --bucket "$$BUCKET" --region $(REGION) \
	    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json > "$$TMP"; \
	  if [ "$$(python3 -c "import json; print(len((json.load(open('$$TMP')) or {}).get('Objects') or []))")" != "0" ]; then \
	    aws s3api delete-objects --bucket "$$BUCKET" --region $(REGION) --delete "file://$$TMP" >/dev/null; \
	  fi; \
	  aws s3api list-object-versions --bucket "$$BUCKET" --region $(REGION) \
	    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json > "$$TMP"; \
	  if [ "$$(python3 -c "import json; print(len((json.load(open('$$TMP')) or {}).get('Objects') or []))")" != "0" ]; then \
	    aws s3api delete-objects --bucket "$$BUCKET" --region $(REGION) --delete "file://$$TMP" >/dev/null; \
	  fi; \
	  rm -f "$$TMP"; \
	fi
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
	  --query "Stacks[0].Outputs[?OutputKey=='ImportsBucketName'].OutputValue" --output text 2>/dev/null); \
	if [ -n "$$BUCKET" ] && [ "$$BUCKET" != "None" ]; then \
	  echo "Vaciando s3://$$BUCKET/"; \
	  aws s3 rm "s3://$$BUCKET/" --recursive --region $(REGION); \
	fi
	$(SAM) delete --stack-name $(STACK) --region $(REGION) --no-prompts
	@for FN in parser normalizer api; do \
	  LG="/aws/lambda/$(STACK)-$$FN-$(STAGE)"; \
	  if aws logs describe-log-groups --log-group-name-prefix "$$LG" --region $(REGION) \
	    --query "logGroups[?logGroupName=='$$LG'] | [0]" --output text 2>/dev/null | grep -qv '^None$$'; then \
	    echo "Borrando log group huerfano $$LG (recreado por Lambda al vaciar el bucket," ; \
	    echo "ya fuera del control de CloudFormation)"; \
	    aws logs delete-log-group --log-group-name "$$LG" --region $(REGION) 2>/dev/null || true; \
	  fi; \
	done
