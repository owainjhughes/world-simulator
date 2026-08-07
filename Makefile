IMAGE := arathia:dev
CLUSTER := ecosystem
NAMESPACE := ecosystem

GENESIS_URL ?= http://localhost:18800
AMQP_URL ?= amqp://dev:dev@localhost:18801/
export GENESIS_URL
export AMQP_URL

.PHONY: run up down logs world ensure-world viewer test unit e2e \
        cluster-up cluster-down deploy build-image load-image apply \
        k8s-run k8s-wait k8s-logs k8s-world k8s-worlds k8s-viewer k8s-e2e

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

k8s-run k8s-logs k8s-world k8s-worlds k8s-viewer k8s-e2e: GENESIS_URL := http://localhost:18810
k8s-run k8s-logs k8s-world k8s-worlds k8s-viewer k8s-e2e: AMQP_URL := amqp://dev:dev@localhost:18811/

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

k8s-logs:
	kubectl logs -n $(NAMESPACE) deployment/clock -f

k8s-wait:
	kubectl rollout status -n $(NAMESPACE) deployment/genesis --timeout=180s
	kubectl rollout status -n $(NAMESPACE) deployment/clock --timeout=180s

k8s-run: deploy k8s-wait ensure-world k8s-viewer

k8s-world:
	curl -X POST $(GENESIS_URL)/worlds

k8s-worlds:
	curl $(GENESIS_URL)/worlds

k8s-viewer:
	uv run python -m app.viewer.menu

k8s-e2e:
	uv run pytest tests/e2e -q
