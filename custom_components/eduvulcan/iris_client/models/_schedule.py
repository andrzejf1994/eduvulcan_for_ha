from datetime import date

from pydantic import BaseModel, Field

from ._clazz import Clazz
from ._distribution import Distribution
from ._employee import Employee
from ._room import Room
from ._subject import Subject
from ._timeslot import Timeslot


class Schedule(BaseModel):
    id: int = Field(alias="Id")
    merge_change_id: int | None = Field(alias="MergeChangeId")
    event: str | None = Field(alias="Event")
    date_: date = Field(alias="DateAt")
    room: Room | None = Field(alias="Room")
    time_slot: Timeslot | None = Field(alias="TimeSlot")
    subject: Subject | None = Field(alias="Subject")
    teacher_primary: Employee | None = Field(alias="TeacherPrimary")
    teacher_secondary: Employee | None = Field(alias="TeacherSecondary")
    teacher_secondary2: Employee | None = Field(alias="TeacherSecondary2")
    clazz: Clazz | None = Field(alias="Clazz")
    distribution: Distribution | None = Field(alias="Distribution")
    pupil_alias: str | None = Field(alias="PupilAlias")
    parent: str | None = Field(alias="Parent")
