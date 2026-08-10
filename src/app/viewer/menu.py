import os
import subprocess
import sys

import httpx

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:18800")
CLOCK_URL = os.environ.get("CLOCK_URL", "http://localhost:18805")


def fetch_worlds() -> list[dict]:
    with httpx.Client(base_url=GENESIS_URL, timeout=10) as client:
        return client.get("/worlds").json()


def fetch_clocks(worlds: list[dict]) -> dict[str, dict]:
    running: dict[str, dict] = {}
    with httpx.Client(base_url=CLOCK_URL, timeout=10) as client:
        for world in worlds:
            try:
                response = client.get(f"/worlds/{world['id']}/clock")
            except httpx.HTTPError:
                continue
            if response.status_code == 200 and (state := response.json())["running"]:
                running[world["id"]] = state
    return running


def show(worlds: list[dict], running: dict[str, dict]) -> None:
    print()
    print(f"  Arathia worlds ({len(running)} running)")
    if not worlds:
        print("  no worlds yet")
    for index, world in enumerate(worlds, start=1):
        clock = running.get(world["id"])
        status = (
            f"day {clock['day']:>3} {clock['hour']:02d}:00 {clock['season']}"
            if clock
            else "idle"
        )
        print(f"  {index}. {world['id'][:8]}  seed {world['seed']:>10}  {status}")
    print()
    print("  [v]iew N   [c]reate   [d]elete N   [r]efresh   [q]uit")


def pick(worlds: list[dict], argument: str) -> dict | None:
    try:
        return worlds[int(argument) - 1]
    except (ValueError, IndexError):
        print("  give a world number from the list")
        return None


def view(world: dict) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "app.viewer.main"],
            env={**os.environ, "WORLD_ID": world["id"]},
        )
    except KeyboardInterrupt:
        pass


def create() -> None:
    with httpx.Client(base_url=GENESIS_URL, timeout=30) as client:
        created = client.post("/worlds").json()
    print(f"  created world {created['world_id'][:8]}")
    print("  a free clock pod will claim it within seconds; otherwise it idles until one is free")


def remove(world: dict) -> None:
    answer = input(f"  delete world {world['id'][:8]}? [y/N] ").strip().lower()
    if answer != "y":
        return
    with httpx.Client(base_url=GENESIS_URL, timeout=10) as client:
        client.delete(f"/worlds/{world['id']}")
    print(f"  deleted {world['id'][:8]}")


def main() -> None:
    while True:
        worlds = fetch_worlds()
        running = fetch_clocks(worlds)
        show(worlds, running)

        try:
            command, _, argument = input("  > ").strip().partition(" ")
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if command == "q":
            return
        if command == "r" or command == "":
            continue
        if command == "c":
            create()
        elif command == "v" and (world := pick(worlds, argument)):
            view(world)
        elif command == "d" and (world := pick(worlds, argument)):
            remove(world)


if __name__ == "__main__":
    main()
