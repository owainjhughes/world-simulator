from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

Season = Literal["winter", "spring", "summer", "autumn"]
Condition = Literal["rain", "snow", "sunshine", "wind"]


class Climate(BaseModel):
    terrain: str
    min_temperature: float
    max_temperature: float
    rainfall: str


class SpeciesProfile(BaseModel):
    id: UUID
    name: str
    region_id: UUID
    diet: Literal["herbivore", "carnivore", "omnivore"]
    min_temperature: float
    max_temperature: float
    habitat: str
    food: list[str]
    prey: list[str]
    transport: Literal["walk", "swim", "fly"]
    speed: float
    migratory: bool


class Event(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    world_id: UUID


class WorldCreated(Event):
    event_type: Literal["WorldCreated"] = "WorldCreated"
    seed: int
    width: int
    height: int

    @property
    def routing_key(self) -> str:
        return "genesis.world.created"


class RegionCreated(Event):
    event_type: Literal["RegionCreated"] = "RegionCreated"
    region_id: UUID
    name: str
    slug: str
    climate: Climate
    tiles: list[tuple[int, int]]

    @property
    def routing_key(self) -> str:
        return "genesis.region.created"


class SpeciesGenerated(Event):
    event_type: Literal["SpeciesGenerated"] = "SpeciesGenerated"
    region_id: UUID
    region_name: str
    species: list[SpeciesProfile]

    @property
    def routing_key(self) -> str:
        return "genesis.species.generated"


class DayArrived(Event):
    event_type: Literal["DayArrived"] = "DayArrived"
    day: int

    @property
    def routing_key(self) -> str:
        return "clock.day.arrived"


class NightArrived(Event):
    event_type: Literal["NightArrived"] = "NightArrived"
    day: int

    @property
    def routing_key(self) -> str:
        return "clock.night.arrived"


class SeasonChanged(Event):
    event_type: Literal["SeasonChanged"] = "SeasonChanged"
    season: Season
    day: int

    @property
    def routing_key(self) -> str:
        return "clock.season.changed"


class SeasonProgressed(Event):
    event_type: Literal["SeasonProgressed"] = "SeasonProgressed"
    season: Season
    day: int
    day_of_season: int

    @property
    def routing_key(self) -> str:
        return "clock.season.progressed"


class TemperatureChanged(Event):
    event_type: Literal["TemperatureChanged"] = "TemperatureChanged"
    region_id: UUID
    region_slug: str
    region_name: str
    celsius: float
    day: int
    hour: int
    season: Season

    @property
    def routing_key(self) -> str:
        return f"clock.temperature.changed.{self.region_slug}"


class WeatherStarted(Event):
    event_type: Literal["WeatherStarted"] = "WeatherStarted"
    region_id: UUID
    region_slug: str
    region_name: str
    condition: Condition

    @property
    def routing_key(self) -> str:
        return f"clock.weather.{self.condition}.started.{self.region_slug}"


class WeatherStopped(Event):
    event_type: Literal["WeatherStopped"] = "WeatherStopped"
    region_id: UUID
    region_slug: str
    region_name: str
    condition: Condition

    @property
    def routing_key(self) -> str:
        return f"clock.weather.{self.condition}.stopped.{self.region_slug}"
