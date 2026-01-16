from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Unit(BaseModel):
    id: int = Field(alias="Id")
    short: str = Field(alias="Short")
    rest_url: str = Field(alias="RestURL")
    name: str = Field(alias="Name")


class Pupil(BaseModel):
    id: int = Field(alias="Id")
    first_name: str = Field(alias="FirstName")
    surname: str = Field(alias="Surname")


class Account(BaseModel):
    unit: Unit = Field(alias="Unit")
    pupil: Pupil = Field(alias="Pupil")
    periods: list["Period"] | None = Field(alias="Periods", default=None)


class Period(BaseModel):
    id: int | None = Field(alias="Id", default=None)
    date_from: date = Field(alias="DateFrom")
    date_to: date = Field(alias="DateTo")
    current: bool = Field(alias="Current")
