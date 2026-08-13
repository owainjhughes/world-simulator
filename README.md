# World Simulator (Arathia)

> Owain Hughes // owainjhughes@gmail.com // github.com/owainjhughes/world-simulator

## Overview

```mermaid
flowchart LR
    User([You]) -->|POST /worlds| Genesis
    Genesis --- GenesisDB[(genesis-db)]
    Clock --- ClockDB[(clock-db)]
    GenesisDB -->|WAL| DebeziumG[Debezium]
    ClockDB -->|WAL| DebeziumC[Debezium]
    DebeziumG -->|world, region and species events| Exchange{{world.events<br/>topic exchange}}
    DebeziumC -->|time, temperature and weather events| Exchange
    Exchange --> ClockQueue[[clock.genesis queue]]
    ClockQueue --> Clock
```

Arathia is a distributed simulation of a living world, built to learn distributed computing.

A world is generated once: three continents and two island groups carved into fourteen named regions, each populated with its own invented species that have diets, temperature preferences, movement types and a food web. From then on the world runs on its own — time passes, seasons turn, temperatures rise and fall with the hour and the season, and weather comes and goes region by region.

Nothing in the system calls anything else directly. Each service announces what has happened as events on RabbitMQ, and any service that cares subscribes. Every service owns its own database.

Here is a world Genesis produced, one character per tile, `.` for open sea:

```
.................................................LLL............................
........................JJJJJ...................LLLLL...........................
.......................JJJJJJJ.................LLLLLLL..........................
......................JJJJJJJJ.................LLLLLLL..........................
.......................JJJJJJJ................LLLLLLL...........................
......................JJJJJJJJJ..............LLLLLLLLL.......AAAAAA.............
.......................JJJJJJJJJJJ........LLLLLLLLLLLL......AAAAAAAA............
........................JJJJJJJJJKKKKKKKKKKLLLLLLLLLL........AAAAAAAA...........
..........................JJJJJJKKKKKKKKKKKKLLLLLLL.........AAAAAAAA............
...........................JJJKKKKKKKKKKKKKKKKKLLLL........AAABBBBBB............
.............FFFF.............KKKKKKKKKKKKKK................BBBBBBBBB...........
..........FFFFFFFFFFF..............KKKKKKK...................CBBBBBBB......N....
.........FFFFFFFFFFFFFFF...................................CCCCCCCCCC....NNNNN..
.........HHFFFFFFFGGGGGGGG................................CCCCCCCCC.........NNN.
.........HHHHHFFGGGGGGGGGGG.........M......................CCCCCCCCC....NNN.NNN.
........HHHHHHHHGGGGGGGGGGG.......MMMMM......................DDDDCCC............
.......HHHHHHHHHHGGGGGGGGG........MMMMM.................DDDDDDDDDDDD............
.......HHHHHHHHHHHIIIIII................................EEDDDDDDDDD.............
.......HHHHHHHHIIIIIIIIIII................................EEEEEDDD..............
...........HHIIIIIIIIIIIII...............................EEEEEEEE...............
...........IIIIIIIIIIII..................................EEEEEEE................
```

Roughly 28% of the map is land. The continent outlines and the position of every region are fixed, so the world is recognisable every time — but the coastline and the borders are generated with noise that shifts each run, so no two worlds are identical.

Ocean is simply any tile no region owns, which makes water a real barrier: something that walks cannot cross it, something that swims can, and something that flies does not care.

## Map

Here is the original painted map that the world creation is based off of:

<img width="1152" height="864" alt="arathia" src="https://github.com/user-attachments/assets/e58f8fcc-1eaa-4c89-a5d4-8e1847474a1d" />

## Features

- Procedural world generation: fourteen regions across three continents and two island groups on an 80x50 grid, with coastlines and borders that shift between runs
- Invented species per region, named from word banks, with randomised traits and wired-up predator/prey relationships
- A world clock with day/night, four seasons, and temperature that follows both the hour and the time of year
- Per-region weather, where snow rather than rain falls if the region is below freezing
- Fully event-driven: services never call each other, fully pub/sub 
- A live terminal viewer that draws the world and updates as it runs
- Runs either on Docker Compose or on a local Kubernetes cluster with Kind

# How to Run Locally

## What you need

- [Docker](https://www.docker.com/products/docker-desktop/)
- [uv](https://docs.astral.sh/uv/) — only if you want to run the services outside containers
- [kind](https://kind.sigs.k8s.io/) and [kubectl](https://kubernetes.io/docs/tasks/tools/) — only for the Kubernetes route

## 🐳 The quick way: Docker Compose

This is the fastest way to see it working.

_Run in the root of this repo:_

```sh
make run
```

That starts RabbitMQ, a Postgres database for each service, both services and a [Debezium](https://debezium.io/) relay for each database, waits for them to be healthy, creates a world if none exists yet, and opens the live viewer.

_The same thing as individual steps:_

```sh
make up       # start the stack
make world    # create a world - always makes a new one
make viewer   # watch it
```

`make world` creates another world every time you run it, while `make run` only creates one if there are none. Extra worlds sit idle until a clock claims them.

If you would rather just read the logs, `make logs` follows the clock:

```
clock  | day 0 06:00 winter - 14 regions, 21 events
clock  | day 0 07:00 winter - 14 regions, 17 events
```

## ☸ Kubernetes with Kind

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
make deploy
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
curl -X POST http://localhost:18810/worlds
kubectl logs -n ecosystem deployment/clock -f
```

Or let one command do the whole thing — deploy, wait for the rollout, create a world if none exists, and open the viewer:

```sh
make k8s-run
```

### 🌍🌍 Running more than one world

Each clock pod runs exactly one world, so the number of clock replicas is the number of worlds actually running. Create a second world, scale the clock, and watch the new pod claim it:

```sh
make k8s-world
kubectl scale deployment/clock -n ecosystem --replicas=2
```

`make k8s-viewer` opens the world menu against the cluster, where you can see which pod-run worlds are ticking, view one, or create and delete them.

# Using the Services

## Where things are

| Service            | Docker Compose       | Kubernetes (Kind)    |
| ------------------ | -------------------- | -------------------- |
| Genesis API        | localhost:18800      | localhost:18810      |
| Swagger UI         | localhost:18800/docs | localhost:18810/docs |
| RabbitMQ dashboard | localhost:18802      | localhost:18812      |
| genesis-db         | localhost:18803      | inside cluster only  |
| clock-db           | localhost:18804      | inside cluster only  |

The RabbitMQ dashboard logs in with `dev` / `dev`. It is worth opening — you can watch queues fill and drain in real time.

## 👁 Watching the world

```sh
make viewer
```

That opens a small menu listing every world. Worlds a clock pod is actively running show their current day and season; worlds no pod has claimed show as idle. From here you can view a world, create a new one, or delete one:

```
  Arathia worlds (1 running)
  1. bb20562b  seed 1542680042  idle
  2. efd5d4eb  seed  961835526  day   2 17:00 winter

  [v]iew N   [c]reate   [d]elete N   [r]efresh   [q]uit
```

The menu learns which worlds are running by listening to the event stream for a few seconds — there is no "running worlds" table anywhere, because the lease that says who runs a world lives in the Clock's own database, and services never read each other's databases. The events themselves are the shared truth.

Deleting a world works the same way in reverse: Genesis removes it and announces `WorldDeleted`, the Clock hears that and drops its copy, and whichever pod was running the world exits its lease and claims another world if one is free.

Picking `v` opens the map viewer for that world. It reads the world's shape from Genesis over HTTP, then subscribes to everything the Clock publishes — events from every other world are ignored. Quit it with Ctrl+C to fall back to the menu.

Each region is drawn in its own colour, with the sea in between. The key is grouped by continent and runs north to south, with each island group listed among the neighbours it sits nearest:

```
  Arathia   day 0  13:00  winter

                        Northsaw
                          Boring Tundra    -16.1C  sunshine
                          Wailfirth         -0.3C  snow
                          Chillcap         -30.4C

   [the map, in           Kuerigo
    colour, with            Korees            -4.6C  sunshine
    ocean between           Wyldvale          10.3C  sunshine wind
    the three               Doreidrassil      11.8C  sunshine wind
    continents]             Trynwyn            8.7C
                            Ranatis           18.5C

                        Eastern Isles
                          Yoonhye Forest    11.0C
                          Denn Arctogh     -24.5C  wind
                          Kagotsuma         20.5C  sunshine
                          Wylenn             7.2C  wind
                          Gloamwoods         5.8C  sunshine
                          Stragglefaun      25.3C  sunshine
```

That is a real frame. Note Wailfirth getting snow while everywhere else with weather gets none.

The viewer holds no state of its own and never talks to a database. It is just another subscriber, which is what makes it a good demonstration of the whole design: you can start it, stop it, and start it again, and the simulation neither knows nor cares.

## 🌍 Genesis API

| Endpoint               | Method | Description                                                  |
| ---------------------- | ------ | ------------------------------------------------------------ |
| `/worlds`              | POST   | Generate a new world. Optional `?seed=` for a repeatable one |
| `/worlds`              | GET    | List every world that has been generated                     |
| `/worlds/{id}`         | DELETE | Delete a world and announce it, so the Clock drops it too    |
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
curl -u dev:dev -X PUT http://localhost:18802/api/queues/%2F/peek.gloamwoods \
  -H "content-type: application/json" -d '{"durable":true}'

curl -u dev:dev -X POST http://localhost:18802/api/bindings/%2F/e/world.events/q/peek.gloamwoods \
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
curl -u dev:dev -X DELETE http://localhost:18802/api/queues/%2F/peek.gloamwoods
```

# Design

## 🎨 Directory Structure

Everything lives under [`src/`](src), split into three layers so it is easy to find what you are looking for:

```
src/
  app/        genesis/   clock/   viewer/
  domain/     world.py  wordbanks.py  seasons.py  weather.py  events.py
  infra/      genesis/  clock/  messaging/
```

- **`domain/`** — the rules of the world, with no I/O at all. World generation, species traits, how temperature moves through a day, when it rains, and the event schemas that make up the shared language. You can read and test all of it without a database or a broker anywhere near it, which is exactly what the unit tests do.
- **`infra/`** — everything that talks to the outside world: database engines, SQLAlchemy models, the RabbitMQ consumer and the outbox.
- **`app/`** — the entrypoints, which wire the two together. HTTP routes for Genesis, the tick loop and event handlers for Clock, the renderer for the viewer.

The services share one codebase and one image, and differ only in the command they are started with. They still deploy separately, own separate databases, and never read each other's tables.

## 📡 Events

Services communicate through a RabbitMQ topic exchange called `world.events`. A publisher never knows who is listening.

No service publishes to RabbitMQ directly, because writing to the database and then publishing are two separate writes, and a crash between them would leave a fact in the database that nobody was ever told about. Instead, each service writes its events into an `outbox` table in the same transaction as the data they describe, and a [Debezium Server](https://debezium.io/documentation/reference/stable/operations/debezium-server.html) instance per database reads them straight out of Postgres's write-ahead log and publishes them — the transactional outbox pattern. The routing key and JSON body on the wire are exactly what the service wrote into the table.

> [!NOTE]
> The `outbox` tables are always empty, and that is not a bug. Each event row is inserted and deleted in the same transaction — Debezium reads the WAL, not the table, so the insert still reaches the broker while the table never grows.

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

Clock listens. It declares its durable queue before anything else, so worlds created while it was down still arrive as events, and every clock pod shares that queue and one database — whichever pod receives a world's creation event registers it for all of them.

Registration and running are two different things. A registered world just sits in the table until a clock pod claims it: each pod takes out a lease on exactly one world (`SELECT ... FOR UPDATE SKIP LOCKED`, so two pods can never grab the same row), renews it on every tick, and simulates only that world. A pod that finds nothing to claim idles and retries. If a pod dies, its lease expires within 30 seconds and the next pod to start picks the world up. So the number of clock replicas is the dial for how many worlds are actually running — `kubectl scale deployment/clock --replicas=3` means three live worlds, assuming three worlds exist to claim.

## 📚 Stack

- **Python 3.13+ with [uv](https://docs.astral.sh/uv/)**
- **[FastAPI](https://fastapi.tiangolo.com/) and [Pydantic](https://docs.pydantic.dev/)**
- **[RabbitMQ](https://www.rabbitmq.com/)**
- **[PostgreSQL](https://www.postgresql.org/)**
- **[Debezium Server](https://debezium.io/)**
- **[Docker Compose](https://docs.docker.com/compose/) and [Kind](https://kind.sigs.k8s.io/).**

# Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

That installs the project itself as well as its dependencies, so `app`, `domain` and `infra` are importable anywhere without setting `PYTHONPATH`.

You can run either service directly against the containerised infrastructure, which is much faster than rebuilding images:

```sh
# Start just the infrastructure (--no-deps stops the Debezium relays dragging in the containerised clock)
docker compose up -d rabbitmq genesis-db clock-db
docker compose up -d --no-deps debezium-genesis debezium-clock

# Run the services on your machine
uv run uvicorn app.genesis.main:app --port 8000
uv run python -m app.clock.main
```

Both read `DATABASE_URL` from the environment. Clock also reads `AMQP_URL` and `TICK_SECONDS`, and the viewer reads `WORLD_ID`.

## 📝 Testing

```sh
make test     # everything
make unit     # domain only, no services needed
make e2e      # needs the stack running
```

The **unit tests** cover the `domain/` layer, which is all pure functions: that seasons fall on the right days, that temperature stays inside a region's climate band, that snow falls below freezing and rain above it, that the same seed rebuilds the same world and a different one moves the borders, and that no predator is ever given prey from another region or a carnivore to hunt.

The **end-to-end tests** need `make up` first, and exercise the whole chain rather than mocking it. They create a real world through the API and check it comes back complete, watch the broker to confirm all 21 creation events are published, and then confirm that exactly one world is emitting temperature readings and that it covers all ten regions. The last one binds a queue to a single region's routing key and asserts nothing from anywhere else arrives.

> [!NOTE]
> The end-to-end tests create real worlds and assume a single clock replica: only one world ever runs, and the extras stay registered but unclaimed and silent. Run them before scaling the clock up, and run `docker compose down -v` if you want to start from an empty slate.

# Looking Forward

This is a work in progress and there is plenty I know is missing or wrong.

- **Clocks do not redistribute worlds.** A pod claims one world at startup and holds it for life, so scaling down orphans a world until a new pod appears, and a `kubectl rollout restart` leaves up to 30 seconds of silence while the old pod's lease expires. Real systems rebalance work when membership changes; this one deliberately does not, yet.
- **Worlds pile up.** Genesis will create as many as you ask for, and each sits registered until a clock claims it. There is still no way to pause, stop or delete a world — only to stop running it.
- **No unit tests for the app layer.** The domain layer is covered, but the tick loop, event handlers and HTTP routes are only exercised end to end.
- **No Ecology or Migration services yet.** These are the interesting ones — creatures living in a region, and creatures crossing between regions, which is where handoffs, sagas and eventual consistency actually bite.
- **No observability.** The plan is OpenTelemetry with SigNoz, so a single world creation can be traced across both services.
- **Raw YAML instead of a Helm chart.** Fine for one environment, but the services are nearly identical, so one templated chart would replace most of `deploy/k8s/`.
- **No dev container or CI.** Everyone sets up their own tools, and nothing is checked automatically on push.
- **The viewer is a terminal program.** A browser-based map, driven by an Observation service that keeps a read model of the world, is the proper version of this.
- **Hand-written database manifests.** Real clusters use operators — CloudNativePG for Postgres, the RabbitMQ Cluster Operator for the broker — which handle clustering, failover and backups. Writing the StatefulSets by hand was worth doing once to understand them, but it is not what you would run.
- **NodePorts instead of an Ingress.** Fine for Kind, not for anything real.
- **A homemade event envelope.** [CloudEvents](https://cloudevents.io/) is the standard for exactly this and would have been the smarter starting point.
