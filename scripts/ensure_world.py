import os

import httpx

#ensure a world exists, if not, create one
with httpx.Client(
    base_url=os.environ.get("GENESIS_URL", "http://localhost:18800"), timeout=30
) as client:
    worlds = client.get("/worlds").json()
    if worlds:
        print(f"{len(worlds)} world(s) exist")
    else:
        created = client.post("/worlds").json()
        print(f"created world {created['world_id']}")
