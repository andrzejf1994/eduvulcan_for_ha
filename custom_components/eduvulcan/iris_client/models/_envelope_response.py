from typing import Any, Union

from pydantic import BaseModel, Field


class ApiStatus(BaseModel):
    code: int = Field(alias="Code")
    message: str = Field(alias="Message")


class EnvelopeResponse(BaseModel):
    envelope_type: str = Field(alias="EnvelopeType")
    envelope: Any = Field(alias="Envelope")
    status: ApiStatus = Field(alias="Status")
    request_id: str = Field(alias="RequestId")
    timestamp: Union[float, int] = Field(alias="Timestamp")
    timestamp_formatted: str = Field(alias="TimestampFormatted")

    class Config:
        arbitrary_types_allowed = True
