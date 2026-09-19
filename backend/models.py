"""Data models for the AI Ship Design Debugger scene."""
from __future__ import annotations

import math
from pydantic import BaseModel, Field, field_validator, model_validator


Vec3 = list[float]  # [x, y, z] in meters, Z-up


class Box(BaseModel):
    """Axis-aligned bounding box."""
    min: Vec3
    max: Vec3

    @model_validator(mode="after")
    def valid_bounds(self):
        if len(self.min) != 3 or len(self.max) != 3:
            raise ValueError("box coordinates must have three components")
        if not all(math.isfinite(v) for v in self.min + self.max):
            raise ValueError("box coordinates must be finite")
        if any(a >= b for a, b in zip(self.min, self.max)):
            raise ValueError("box min must be smaller than max on each axis")
        return self


class RoomMeta(BaseModel):
    name: str
    units: str = "m"
    up_axis: str = "z"
    room: Box


class Rules(BaseModel):
    min_pipe_clearance_mm: float = 300
    min_pipe_to_pipe_clearance_mm: float = 50
    default_maintenance_clearance_mm: float = 800


class Structure(BaseModel):
    id: str
    name: str
    type: str  # deck | frame | bulkhead ...
    box: Box
    role: str | None = None


class Room(BaseModel):
    """A rectangular room region; furniture must stay inside one room."""
    id: str
    name: str
    box: Box


class Equipment(BaseModel):
    id: str
    name: str
    type: str  # pump | engine | heat_exchanger | generator ...
    box: Box
    rotation: int = 0  # yaw in degrees (0/90/180/270); box is always the world AABB
    maintenance_clearance_mm: float | None = None

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, value: int) -> int:
        if value % 90:
            raise ValueError("rotation must be a multiple of 90 degrees")
        return value % 360

    @field_validator("maintenance_clearance_mm")
    @classmethod
    def validate_clearance(cls, value: float | None) -> float | None:
        if value is not None and (value < 0 or not math.isfinite(value)):
            raise ValueError("maintenance_clearance_mm must be finite and non-negative")
        return value


class Pipe(BaseModel):
    id: str
    name: str
    system: str
    diameter_mm: float
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    path: list[Vec3]  # centerline waypoints

    model_config = {"populate_by_name": True}


class Scene(BaseModel):
    meta: RoomMeta
    rules: Rules
    rooms: list[Room] = []
    structures: list[Structure]
    equipment: list[Equipment]
    pipes: list[Pipe] = []

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [obj.id for obj in self.equipment + self.structures + self.pipes + self.rooms]
        if any(not oid or oid == "room" for oid in ids) or len(ids) != len(set(ids)):
            raise ValueError("scene IDs must be unique, non-empty, and not 'room'")
        return self
