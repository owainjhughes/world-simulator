CLUSTER := ecosystem
NAMESPACE := ecosystem
RELEASE := arathia
CHART := deploy/helm/arathia
IMAGE := arathia:dev

GENESIS_URL ?= http://localhost:18800
CLOCK_URL ?= http://localhost:18805
AMQP_URL ?= amqp://dev:dev@localhost:18801/
export GENESIS_URL
export CLOCK_URL
export AMQP_URL

.PHONY: run up down logs logs-ecology world ensure-world viewer \
        clean-cluster create-cluster \
        build-docker load-docker deploy-helm clean-helm deploy-local \
        render-helm dev \
        run-kind logs-kind world-kind worlds-kind viewer-kind e2e-kind \
        test lint unit e2e

# Docker Compose

# Start the stack, create a world if there is none, and open the viewer
run: up ensure-world viewer

# Start every container and wait until they are healthy
up:
	docker compose up -d --build --wait

# Stop and remove every container
down:
	docker compose down

# Follow the clock's logs
logs:
	docker compose logs -f clock

# Follow Ecology's logs
logs-ecology:
	docker compose logs -f ecology

# Create a world, always a new one
world:
	curl -X POST $(GENESIS_URL)/worlds

# Create a world only if none exists yet
ensure-world:
	uv run python scripts/ensure_world.py

# Open the live viewer
viewer:
	uv run python -m app.viewer.menu

# Init

# Delete the Kind cluster
clean-cluster:
	kind delete cluster --name $(CLUSTER)

# Create the Kind cluster with its port mappings
create-cluster:
	kind create cluster --config deploy/kind-cluster.yaml

# Local Deployment

# Build the Docker image
build-docker:
	docker build -t $(IMAGE) -f deploy/docker/Dockerfile .

# Load the image into the Kind cluster, which cannot pull from your machine
load-docker:
	kind load docker-image $(IMAGE) --name $(CLUSTER)

# Install or upgrade the Helm chart
deploy-helm:
	helm upgrade --install $(RELEASE) $(CHART) \
		--namespace $(NAMESPACE) --create-namespace \
		--set image=$(IMAGE) --wait --timeout 10m

# Uninstall the Helm chart, leaving the cluster in place
clean-helm:
	helm uninstall $(RELEASE) --namespace $(NAMESPACE)

# Build, load and deploy in one go
deploy-local: build-docker load-docker deploy-helm

# Development

# Render the chart to a file and open it, which is the quickest way to debug a template
render-helm:
	helm template $(RELEASE) $(CHART) --namespace $(NAMESPACE) > deploy/helm/render.yaml && code deploy/helm/render.yaml

# Watch the source and redeploy on every save
dev:
	skaffold dev

# Kind-scoped helpers

run-kind logs-kind world-kind worlds-kind viewer-kind e2e-kind: GENESIS_URL := http://localhost:18810
run-kind logs-kind world-kind worlds-kind viewer-kind e2e-kind: CLOCK_URL := http://localhost:18813
run-kind logs-kind world-kind worlds-kind viewer-kind e2e-kind: AMQP_URL := amqp://dev:dev@localhost:18811/

# Deploy to the cluster, create a world if there is none, and open the viewer
run-kind: deploy-local ensure-world viewer-kind

# Follow the clock's logs in the cluster
logs-kind:
	kubectl logs -n $(NAMESPACE) deployment/clock -f

# Create a world in the cluster, always a new one
world-kind:
	curl -X POST $(GENESIS_URL)/worlds

# List the worlds in the cluster
worlds-kind:
	curl $(GENESIS_URL)/worlds

# Open the live viewer against the cluster
viewer-kind:
	uv run python -m app.viewer.menu

# Run the end-to-end tests against the cluster
e2e-kind:
	uv run pytest tests/e2e -q

# Tests

# Lint and run every test
test: lint unit e2e

# Check formatting and lint rules
lint:
	uv run ruff check .

# Run the domain tests, which need nothing running
unit:
	uv run pytest tests/unit -q

# Run the end-to-end tests, which need the stack running
e2e:
	uv run pytest tests/e2e -q
