from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

Season = Literal["winter", "spring", "summer", "autumn"]
Condition = Literal["rain", "snow", "sunshine", "wind"]
Diet = Literal["herbivore", "carnivore", "omnivore"]
DeathCause = Literal["starved", "froze", "scorched", "killed", "aged"]


class Climate(BaseModel):
    terrain: str
    min_temperature: float
    max_temperature: float
    rainfall: str
    plants: list[str]


class SpeciesProfile(BaseModel):
    id: UUID
    name: str
    region_id: UUID
    diet: Diet
    min_temperature: float
    max_temperature: float
    habitat: str
    food: list[str] = []
    prey: list[str] = []
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
    regions: int
    species: int

    @property
    def routing_key(self) -> str:
        return "genesis.world.created"


class WorldDeleted(Event):
    event_type: Literal["WorldDeleted"] = "WorldDeleted"

    @property
    def routing_key(self) -> str:
        return "genesis.world.deleted"


class RegionCreated(Event):
    event_type: Literal["RegionCreated"] = "RegionCreated"
    region_id: UUID
    name: str
    slug: str
    continent: str
    colour: str
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


class RegionCensus(Event):
    event_type: Literal["RegionCensus"] = "RegionCensus"
    region_id: UUID
    region_slug: str
    region_name: str
    day: int
    hour: int
    herbivores: list[tuple[int, int]] = []
    carnivores: list[tuple[int, int]] = []
    omnivores: list[tuple[int, int]] = []

    @property
    def routing_key(self) -> str:
        return f"ecology.census.{self.region_slug}"


class CreatureBorn(Event):
    event_type: Literal["CreatureBorn"] = "CreatureBorn"
    region_id: UUID
    region_slug: str
    region_name: str
    species: str

    @property
    def routing_key(self) -> str:
        return f"ecology.creature.born.{self.region_slug}"


class CreatureDied(Event):
    event_type: Literal["CreatureDied"] = "CreatureDied"
    region_id: UUID
    region_slug: str
    region_name: str
    species: str
    cause: DeathCause
    killed_by: str | None = None

    @property
    def routing_key(self) -> str:
        return f"ecology.creature.died.{self.cause}.{self.region_slug}"


class SpeciesExtinct(Event):
    event_type: Literal["SpeciesExtinct"] = "SpeciesExtinct"
    region_id: UUID
    region_slug: str
    region_name: str
    species: str

    @property
    def routing_key(self) -> str:
        return f"ecology.species.extinct.{self.region_slug}"


class ComfortChanged(Event):
    event_type: Literal["ComfortChanged"] = "ComfortChanged"
    region_id: UUID
    region_slug: str
    region_name: str
    species: str
    state: Literal["stressed", "eased"]
    celsius: float

    @property
    def routing_key(self) -> str:
        return f"ecology.comfort.{self.state}.{self.region_slug}"
