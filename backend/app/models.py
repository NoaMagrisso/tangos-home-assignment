from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Relation(BaseModel):
    target_id: str
    type: str
    note: str | None


class Entity(BaseModel):
    id: str
    name: str
    aliases: list[str]
    type: str
    countries: list[str]
    programs: list[str]
    list_date: date
    remarks: str | None
    relations: list[Relation]
