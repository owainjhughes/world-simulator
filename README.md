# Arathia

> Owain Hughes // owainjhughes@gmail.com // github.com/owainjhughes/arathia

## Overview

```mermaid
flowchart LR
    User([You]) -->|POST /worlds| Genesis
    Genesis -->|world, region and species events| Exchange{{world.events<br/>topic exchange}}
    Exchange --> ClockQueue[[clock.genesis queue]]
    ClockQueue --> Clock
    Clock -->|time, temperature and weather events| Exchange
    Genesis --- GenesisDB[(genesis-db)]
    Clock --- ClockDB[(clock-db)]
```

Arathia is a distributed simulation of a living world, built to learn distributed computing properly rather than to ship a product.

A world is generated once: a tile grid carved into ten named regions, each populated with its own invented species that have diets, temperature preferences, movement types and a food web. From then on the world runs on its own — time passes, seasons turn, temperatures rise and fall with the hour and the season, and weather comes and goes region by region.

Nothing in the system calls anything else directly. Each service announces what has happened as events on RabbitMQ, and any service that cares subscribes. Every service owns its own database and nobody reads anyone else's.

Here is a world Genesis actually produced, drawn as one character per tile:

```
AAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBCCCCCCCCCCCCCCCCCCC
AAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBCCCCCCCCCCCCCCCCCCCC
DDAAAAAAAAAAAAAAAAEEEEBBBBBBBBBBBBBBBBBCCCCCCCCCCCCCCCCCCCCC
DDDDDDDDDDDDDDAAEEEEEEEEEEBBBBBBBBBBBBCCCCCCCCCCCCCCCCCCCCCC
DDDDDDDDDDDDDDDDEEEEEEEEEEEEEEBBBBBFFFFFCCCCCCCCCCCCCCCCCCCC
DDDDDDDDDDDDDDDEEEEEEEEEEEEEEEEEFFFFFFFFFFFFCCCCCCCCCCCGGGGG
DDDDDDDDDDDDHHHHEEEEEEEEEEEEEEEFFFFFFFFFFFFFFGGGGGGGGGGGGGGG
HHHHHHHHHHHHHHHHHHHHHHHEEEIIIIIIIIIIFFFFFFFJJJGGGGGGGGGGGGGG
HHHHHHHHHHHHHHHHHHHHHHHHIIIIIIIIIIIIIIIIJJJJJJJJJJGGGGGGGGGG
HHHHHHHHHHHHHHHHHHHHHHHIIIIIIIIIIIIIIIIJJJJJJJJJJJJJJJJJJJJJ
```

The region seeds are fixed, so the map is recognisable every time, but each run jitters how strongly each region pushes against its neighbours — so the borders move and no two worlds are identical.

## Features

- Procedural world generation: ten regions on a 60x40 tile grid, with borders that shift between runs
- Invented species per region, named from word banks, with randomised traits and wired-up predator/prey relationships
- A world clock with day/night, four seasons, and temperature that follows both the hour and the time of year
- Per-region weather, where snow rather than rain falls if the region is below freezing
- Fully event-driven: services never call each other, they publish facts and subscribe to the ones they care about
- A live terminal viewer that draws the world and updates as it runs
- Runs either on Docker Compose or on a local Kubernetes cluster with Kind

# How to Run Locally

## What you need

- [Docker](https://www.docker.com/products/docker-desktop/)
- [uv](https://docs.astral.sh/uv/) — only if you want to run the services outside containers
- [kind](https://kind.sigs.k8s.io/) and [kubectl](https://kubernetes.io/docs/tasks/tools/) — only for the Kubernetes route

## 🐳 The quick way: Docker Compose

This is the fastest way to see the whole thing working.

_Run in the root of this repo:_

```sh
make up
make world
make viewer
```

That brings up RabbitMQ, a Postgres database for each service and both services, generates a world, and opens the live viewer.

_The same thing without `make`:_

```sh
docker compose up -d --build
curl -X POST http://localhost:8000/worlds
uv run python -m app.viewer.main
```

If you would rather just read the logs, `make logs` follows the clock:

```
clock  | day 0 06:00 winter - 10 regions, 17 events
clock  | day 0 07:00 winter - 10 regions, 13 events
```

## ☸ The interesting way: Kubernetes with Kind

### 🛞 Create a cluster

The cluster config is in [deploy/kind-cluster.yaml](deploy/kind-cluster.yaml). It creates one control plane and two workers, and maps two ports out to your machine so you can reach the API and the RabbitMQ dashboard.

```sh
kind create cluster --config deploy/kind-cluster.yaml
```

### 🔑 Create the credentials file

> [!IMPORTANT]
> `deploy/k8s/10-credentials.yaml` is deliberately **not** committed, because it holds passwords. You need to create it yourself before deploying.

_Save this as `deploy/k8s/10-credentials.yaml`:_

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: credentials
  namespace: ecosystem
type: Opaque
stringData:
  postgres-user: dev
  postgres-password: dev
  rabbitmq-user: dev
  rabbitmq-password: dev
  amqp-url: amqp://dev:dev@rabbitmq:5672/
  genesis-database-url: postgresql+asyncpg://dev:dev@genesis-db:5432/genesis
  clock-database-url: postgresql+asyncpg://dev:dev@clock-db:5432/clock
```

### 🚀 Build, load and deploy

Kind runs its own container registry inside the cluster, so images built on your machine have to be loaded in explicitly — otherwise Kubernetes will try to pull them from Docker Hub and fail. One command does all three steps:

```sh
make deploy-local
```

_Or by hand:_

```sh
# Build the image - one image serves both services
docker build -t arathia:dev -f deploy/docker/Dockerfile .

# Load it into the cluster
kind load docker-image arathia:dev --name ecosystem

# Deploy everything
kubectl apply -f deploy/k8s/
```

> [!TIP]
> There is only one image. Genesis and Clock are the same codebase started with different commands, which each Deployment sets for itself.

> [!NOTE]
> **Genesis and Clock will crash a few times on first deploy, and that is fine.** They start before their databases are ready, fail, and Kubernetes restarts them until it works. You will see `CrashLoopBackOff` for a minute or so before everything settles. This is the intended way to handle startup ordering in Kubernetes.

Watch them come up:

```sh
kubectl get pods -n ecosystem -w
```

Once everything is `Running`, create a world and watch it go:

```sh
curl -X POST http://localhost:8080/worlds
kubectl logs -n ecosystem deployment/clock -f
```

# Using the Services

## Where things are

| Service            | Docker Compose      | Kubernetes (Kind)   |
| ------------------ | ------------------- | ------------------- |
| Genesis API        | localhost:8000      | localhost:8080      |
| Swagger UI         | localhost:8000/docs | localhost:8080/docs |
| RabbitMQ dashboard | localhost:15672     | localhost:15673     |
| genesis-db         | localhost:5432      | inside cluster only |
| clock-db           | localhost:5433      | inside cluster only |

The RabbitMQ dashboard logs in with `dev` / `dev`. It is worth opening — you can watch queues fill and drain in real time.

## 👁 Watching the world

The viewer draws the map and updates it live as events arrive. It reads the world's shape from Genesis over HTTP, then subscribes to everything the Clock publishes.

```sh
make viewer
```

Each region is a block of colour, with its current temperature and weather listed beside it:

```
  Arathia   day 1  09:00  winter

  ███████████░░░░░░░░▒▒▒▒▒▒▒▒▒    Denn Arctogh     -31.3C  sunshine wind
  ███████████░░░░░░░░▒▒▒▒▒▒▒▒▒    Boring Tundra    -21.2C  snow wind
  ███████████░░░░░░░▒▒▒▒▒▒▒▒▒▒    Korees            -8.2C  wind
  ██████░░░░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒    Wylenn             5.3C
  ███░░░░░░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Gloamwoods         1.2C  sunshine wind
  ░░░░░░░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Trynwyn            7.3C  sunshine wind
  ░░░░░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Yoonhye Forest     5.9C  wind
  ░░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Ranatis           12.3C  wind
  ░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Stragglefaun      22.5C  rain
  ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒    Kagotsuma         10.4C  rain wind
```

The viewer holds no state of its own and never talks to a database. It is just another subscriber, which is what makes it a good demonstration of the whole design: you can start it, stop it, and start it again, and the simulation neither knows nor cares.

## 🌍 Genesis API

| Endpoint               | Method | Description                                                  |
| ---------------------- | ------ | ------------------------------------------------------------ |
| `/worlds`              | POST   | Generate a new world. Optional `?seed=` for a repeatable one |
| `/worlds`              | GET    | List every world that has been generated                     |
| `/worlds/{id}/regions` | GET    | The regions of a world, with climate and tiles               |
| `/worlds/{id}/species` | GET    | Every species in a world, with its full trait sheet          |
| `/health`              | GET    | Health check, used by the Kubernetes probes                  |
| `/docs`                | GET    | Swagger UI                                                   |

Creating a world returns a summary:

```json
{
  "world_id": "9a4a31cf-4710-4534-b8be-54160f056273",
  "seed": 1263625503,
  "regions": 10,
  "species": 76
}
```

And the species come out looking like this:

```
Bramwing             carnivore  walk  speed 1.4   -36.1..-2.7C  resident
                     hunts: Glintcrawl, Glintquill, Murktail Wanderer
Glintcrawl           herbivore  walk  speed 2.4   -33.9..1.3C   migratory
                     eats: thistle, sapbark, lichen
Siltcreep            carnivore  swim  speed 7.4   -29.5..-4.3C  migratory
                     hunts: Murktail Wanderer, Glintquill
```

## 📬 Watching a single region's events

Every region-scoped event ends its routing key with the region name, which means you can subscribe to exactly one region and ignore the other nine. This is how the future Ecology services will each listen only to their own patch of the world.

To see it, create a queue bound to just one region and peek at what lands in it:

```sh
# Create a queue that only receives Gloamwoods events
curl -u dev:dev -X PUT http://localhost:15672/api/queues/%2F/peek.gloamwoods \
  -H "content-type: application/json" -d '{"durable":true}'

curl -u dev:dev -X POST http://localhost:15672/api/bindings/%2F/e/world.events/q/peek.gloamwoods \
  -H "content-type: application/json" -d '{"routing_key":"clock.#.gloamwoods"}'
```

Wait a few seconds, then read the messages in the RabbitMQ dashboard under **Queues → peek.gloamwoods → Get messages**. You will see only Gloamwoods, and nothing from anywhere else:

```
[clock.temperature.changed.gloamwoods]   Gloamwoods   0.4C
[clock.temperature.changed.gloamwoods]   Gloamwoods  -0.7C
[clock.weather.snow.started.gloamwoods]  Gloamwoods   snow
```

Note the snow — Gloamwoods had dropped below freezing, so the weather came out as snow rather than rain.

_Remember to delete the queue when you are done, or it will fill up forever:_

```sh
curl -u dev:dev -X DELETE http://localhost:15672/api/queues/%2F/peek.gloamwoods
```

# Design

## 🎨 How the code is laid out

Everything lives under [`src/`](src), split into three layers so it is easy to find what you are looking for:

```
src/
  app/        genesis/   clock/   viewer/
  domain/     world.py  wordbanks.py  seasons.py  weather.py  events.py
  infra/      genesis/  clock/  messaging/
```

- **`domain/`** — the rules of the world, with no I/O at all. World generation, species traits, how temperature moves through a day, when it rains, and the event schemas that make up the shared language. You can read and test all of it without a database or a broker anywhere near it, which is exactly what the unit tests do.
- **`infra/`** — everything that talks to the outside world: database engines, SQLAlchemy models, and the RabbitMQ publisher and consumer.
- **`app/`** — the entrypoints, which wire the two together. HTTP routes for Genesis, the tick loop and event handlers for Clock, the renderer for the viewer.

The services share one codebase and one image, and differ only in the command they are started with. They still deploy separately, own separate databases, and never read each other's tables.

## 📡 Events

Services communicate through a RabbitMQ topic exchange called `world.events`. A publisher never knows who is listening.

| Event                | Routing key                                 | Published by |
| -------------------- | ------------------------------------------- | ------------ |
| `WorldCreated`       | `genesis.world.created`                     | Genesis      |
| `RegionCreated`      | `genesis.region.created`                    | Genesis      |
| `SpeciesGenerated`   | `genesis.species.generated`                 | Genesis      |
| `DayArrived`         | `clock.day.arrived`                         | Clock        |
| `NightArrived`       | `clock.night.arrived`                       | Clock        |
| `SeasonChanged`      | `clock.season.changed`                      | Clock        |
| `SeasonProgressed`   | `clock.season.progressed`                   | Clock        |
| `TemperatureChanged` | `clock.temperature.changed.{region}`        | Clock        |
| `WeatherStarted`     | `clock.weather.{condition}.started.{region}`| Clock        |
| `WeatherStopped`     | `clock.weather.{condition}.stopped.{region}`| Clock        |

Putting the region at the end of the routing key is what makes `clock.#.wylenn` work as a subscription.

## ⏳ How time works

One tick advances the world by one simulated hour, and a tick fires every two real seconds by default (`TICK_SECONDS`). A season is 30 days, so a year is 120 days — about an hour and a half of real time to watch a full cycle.

Temperature is not random. Each region has a climate band, and the reading combines where you are in the year with where you are in the day, plus a little noise. So Denn Arctogh is bitter all year and merely unpleasant in summer, while Ranatis swings wildly between night and afternoon.

## 🗄 A database each

Genesis and Clock have their own Postgres instances and cannot see each other's tables. This is deliberate and it is the source of most of what makes distributed systems interesting: if Clock wants to know what regions exist, it cannot run a join — it has to listen for the events, or ask over HTTP.

Clock does both. It declares its durable queue before anything else, so events published while it was busy still arrive. But if it starts with an empty database and finds it missed the world entirely, it falls back to asking Genesis directly over HTTP. Either way it ends up knowing the world.

## 📚 Stack

- **Python 3.13+ with [uv](https://docs.astral.sh/uv/)** for a workspace monorepo.
  - One lockfile at the root, one command (`uv sync --all-packages`) to set everything up.
  - Services depend on the shared libraries directly, with nothing published to a registry.
- **[FastAPI](https://fastapi.tiangolo.com/) and [Pydantic](https://docs.pydantic.dev/)** for the Genesis API and every event schema.
  - Pydantic validates messages at the edge, so anything past that point is guaranteed well-formed.
  - Free Swagger documentation is a nice bonus.
- **[RabbitMQ](https://www.rabbitmq.com/)** as the message broker.
  - Chosen over Kafka to start, because queue semantics — bindings, acknowledgements, dead-letter queues — are simpler to learn without a cluster to run.
  - Topic exchanges give the wildcard routing that per-region subscriptions need.
- **[PostgreSQL](https://www.postgresql.org/) with [SQLAlchemy 2.0 async](https://docs.sqlalchemy.org/) and asyncpg.**
  - One database per service, never shared.
- **[Docker Compose](https://docs.docker.com/compose/) and [Kind](https://kind.sigs.k8s.io/).**
  - Compose for quick iteration; Kind for the real thing, with StatefulSets, Secrets, probes and a genuine multi-node cluster.

# Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

That installs the project itself as well as its dependencies, so `app`, `domain` and `infra` are importable anywhere without setting `PYTHONPATH`.

You can run either service directly against the containerised infrastructure, which is much faster than rebuilding images:

```sh
# Start just the infrastructure
docker compose up -d rabbitmq genesis-db clock-db

# Run the services on your machine
uv run uvicorn app.genesis.main:app --port 8000
uv run python -m app.clock.main
```

Both read `DATABASE_URL` and `AMQP_URL` from the environment. Clock also reads `GENESIS_URL` and `TICK_SECONDS`.

## 📝 Testing

```sh
make test     # everything
make unit     # domain only, no services needed
make e2e      # needs the stack running
```

The **unit tests** cover the `domain/` layer, which is all pure functions: that seasons fall on the right days, that temperature stays inside a region's climate band, that snow falls below freezing and rain above it, that the same seed rebuilds the same world and a different one moves the borders, and that no predator is ever given prey from another region or a carnivore to hunt.

The **end-to-end tests** need `make up` first, and exercise the whole chain rather than mocking it. They create a real world through the API and check it comes back complete, watch the broker to confirm all 21 creation events are published, and then wait for the Clock to notice the new world and start emitting temperature readings for all ten regions. The last one binds a queue to a single region's routing key and asserts nothing from anywhere else arrives.

> [!NOTE]
> The end-to-end tests create real worlds, and the Clock will keep simulating every world it has ever been told about. Run `make down` and `make up` if you want to start from an empty slate.

# Looking Forward

This is a work in progress and there is plenty I know is missing or wrong.

- **Clock is a singleton and only crudely protected.** The tick loop advances a single row in the database, so two replicas would both advance it and time would move at double speed. The Deployment uses the `Recreate` strategy so a rolling update cannot briefly run two pods, but nothing stops someone setting `replicas: 2`. A lock on the tick, or a proper leader election lease, would make it impossible rather than merely unlikely.
- **Nothing limits how many worlds run at once.** Genesis will create as many as you ask for and the Clock simulates every one it hears about, forever. There is no way to pause, stop or delete a world.
- **No unit tests for the app layer.** The domain layer is covered, but the tick loop, event handlers and HTTP routes are only exercised end to end.
- **Events are published after the database commit, not with it.** If a service dies in the gap, the data exists but nobody is ever told. The fix is the transactional outbox pattern: write events to a table in the same transaction, and have a separate process publish them.
- **No Ecology or Migration services yet.** These are the interesting ones — creatures living in a region, and creatures crossing between regions, which is where handoffs, sagas and eventual consistency actually bite.
- **No observability.** The plan is OpenTelemetry with SigNoz, so a single world creation can be traced across both services.
- **Raw YAML instead of a Helm chart.** Fine for one environment, but the services are nearly identical, so one templated chart would replace most of `deploy/k8s/`.
- **No dev container or CI.** Everyone sets up their own tools, and nothing is checked automatically on push.
- **The viewer is a terminal program.** A browser-based map, driven by an Observation service that keeps a read model of the world, is the proper version of this.
- **Hand-written database manifests.** Real clusters use operators — CloudNativePG for Postgres, the RabbitMQ Cluster Operator for the broker — which handle clustering, failover and backups. Writing the StatefulSets by hand was worth doing once to understand them, but it is not what you would run.
- **NodePorts instead of an Ingress.** Fine for Kind, not for anything real.
- **A homemade event envelope.** [CloudEvents](https://cloudevents.io/) is the standard for exactly this and would have been the smarter starting point.
