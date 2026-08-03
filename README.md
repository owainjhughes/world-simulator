# Ecosystem simulation

A distributed simulation of a fantasy world: ten regions, generated species with food webs, seasons and weather. Services communicate over RabbitMQ.

## Services

| Service | Role |
|---|---|
| `genesis` | Generates the world (tile grid, regions, species) and publishes it as events. FastAPI on port 8000. |
| `almanac` | Owns the world clock. Ticks time, publishes season, temperature and weather events per region. |

Shared packages live in `libs/`: `contracts` (event schemas) and `messaging` (RabbitMQ publisher/consumer).

Each service is laid out in three layers: `domain` holds rules with no I/O, `infra` holds database models and adapters, and `app` wires them together and provides the entrypoint.

## Running with Docker Compose

```
docker compose up -d --build
curl -X POST http://localhost:8000/worlds
docker compose logs -f almanac
```

RabbitMQ management UI: http://localhost:15672 (dev / dev)

## Running on Kubernetes (Kind)

```
kind create cluster --config k8s/kind-cluster.yaml
docker build -t ecosystem/genesis:dev -f services/genesis/Dockerfile .
docker build -t ecosystem/almanac:dev -f services/almanac/Dockerfile .
kind load docker-image ecosystem/genesis:dev ecosystem/almanac:dev --name ecosystem
kubectl apply -f deploy/k8s/
```

```
kubectl get pods -n ecosystem
kubectl logs -n ecosystem deployment/almanac -f
curl -X POST http://localhost:8080/worlds
```

Genesis is exposed on host port 8080, RabbitMQ management on 15673.

## Local development

```
uv sync --all-packages
uv run uvicorn genesis.app.main:app --port 8000
uv run python -m almanac.app.main
```

Both read `DATABASE_URL`, `AMQP_URL`; almanac also reads `GENESIS_URL` and `TICK_SECONDS`.
