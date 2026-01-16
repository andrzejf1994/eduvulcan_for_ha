from datetime import date

from pydantic import BaseModel, Field


class Vacation(BaseModel):
    name: str = Field(alias="Name")
    date_from: date = Field(alias="DateFrom")
    date_to: date = Field(alias="DateTo")
