IMAGE := arathia:dev
CLUSTER := ecosystem
NAMESPACE := ecosystem

GENESIS_URL ?= http://localhost:18800
CLOCK_URL ?= http://localhost:18805
AMQP_URL ?= amqp://dev:dev@localhost:18801/
export GENESIS_URL
export CLOCK_URL
export AMQP_URL

.PHONY: run up down logs world ensure-world viewer test unit e2e \
        cluster-up cluster-down deploy build-image load-image apply \
        kind-run kind-wait kind-logs kind-world kind-worlds kind-viewer kind-e2e

# ---- Docker Compose ----

run: up ensure-world viewer

up:
	docker compose up -d --build --wait

down:
	docker compose down

logs:
	docker compose logs -f clock

world:
	curl -X POST $(GENESIS_URL)/worlds

ensure-world:
	uv run python scripts/ensure_world.py

viewer:
	uv run python -m app.viewer.menu

test: unit e2e

unit:
	uv run pytest tests/unit -q

e2e:
	uv run pytest tests/e2e -q

# ---- Kind ----

kind-run kind-logs kind-world kind-worlds kind-viewer kind-e2e: GENESIS_URL := http://localhost:18810
kind-run kind-logs kind-world kind-worlds kind-viewer kind-e2e: CLOCK_URL := http://localhost:18813
kind-run kind-logs kind-world kind-worlds kind-viewer kind-e2e: AMQP_URL := amqp://dev:dev@localhost:18811/

cluster-up:
	kind create cluster --config deploy/kind-cluster.yaml

cluster-down:
	kind delete cluster --name $(CLUSTER)

build-image:
	docker build -t $(IMAGE) -f deploy/docker/Dockerfile .

load-image:
	kind load docker-image $(IMAGE) --name $(CLUSTER)

apply:
	kubectl apply -f deploy/k8s/

deploy: build-image load-image apply
	kubectl rollout restart -n $(NAMESPACE) deployment/genesis deployment/clock

kind-logs:
	kubectl logs -n $(NAMESPACE) deployment/clock -f

kind-wait:
	kubectl rollout status -n $(NAMESPACE) deployment/genesis --timeout=180s
	kubectl rollout status -n $(NAMESPACE) deployment/clock --timeout=180s

kind-run: deploy kind-wait ensure-world kind-viewer

kind-world:
	curl -X POST $(GENESIS_URL)/worlds

kind-worlds:
	curl $(GENESIS_URL)/worlds

kind-viewer:
	uv run python -m app.viewer.menu

kind-e2e:
	uv run pytest tests/e2e -q
