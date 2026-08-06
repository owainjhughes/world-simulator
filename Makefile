IMAGE := arathia:dev
CLUSTER := ecosystem
NAMESPACE := ecosystem

.PHONY: up down logs viewer world test unit e2e build-docker create-cluster load-docker deploy-k8s deploy-local delete-cluster

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f clock

world:
	curl -X POST http://localhost:8000/worlds

viewer:
	uv run python -m app.viewer.main

test: unit e2e

unit:
	uv run pytest tests/unit -q

e2e:
	uv run pytest tests/e2e -q

build-docker:
	docker build -t $(IMAGE) -f deploy/docker/Dockerfile .

create-cluster:
	kind create cluster --config deploy/kind-cluster.yaml

delete-cluster:
	kind delete cluster --name $(CLUSTER)

load-docker:
	kind load docker-image $(IMAGE) --name $(CLUSTER)

deploy-k8s:
	kubectl apply -f deploy/k8s/

deploy-local: build-docker load-docker deploy-k8s
	kubectl rollout restart -n $(NAMESPACE) deployment/genesis deployment/clock
