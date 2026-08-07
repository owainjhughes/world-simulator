IMAGE := arathia:dev
CLUSTER := ecosystem
NAMESPACE := ecosystem

GENESIS_URL ?= http://localhost:8000
AMQP_URL ?= amqp://dev:dev@localhost:5672/
export GENESIS_URL
export AMQP_URL

.PHONY: up down logs world viewer test unit e2e \
        cluster-up cluster-down deploy build-image load-image apply \
        k8s-logs k8s-world k8s-viewer k8s-e2e

# ---- Docker Compose ----

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f clock

world:
	curl -X POST $(GENESIS_URL)/worlds

viewer:
	uv run python -m app.viewer.main

test: unit e2e

unit:
	uv run pytest tests/unit -q

e2e:
	uv run pytest tests/e2e -q

# ---- Kubernetes on Kind ----

k8s-logs k8s-world k8s-viewer k8s-e2e: GENESIS_URL := http://localhost:8080
k8s-logs k8s-world k8s-viewer k8s-e2e: AMQP_URL := amqp://dev:dev@localhost:5673/

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

k8s-world:
	curl -X POST $(GENESIS_URL)/worlds

k8s-viewer:
	uv run python -m app.viewer.main

k8s-e2e:
	uv run pytest tests/e2e -q
