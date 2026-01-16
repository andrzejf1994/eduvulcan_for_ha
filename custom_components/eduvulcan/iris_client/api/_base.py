from datetime import date, datetime

from .._http_client import HttpClient
from ..credentials import ICredential
from ..models import Account, Exam, Homework, Schedule

EPOCH_START_DATETIME = datetime(1970, 1, 1, 1, 0, 0)
INT_MIN = -2_147_483_648
DEFAULT_PAGE_SIZE = 500


class IrisApi:
    _http: HttpClient
    _credential: ICredential

    def __init__(self, credential: ICredential):
        self._credential = credential

    async def get_accounts(self, pupil_id: int | None = None) -> list[Account]:
        envelope = await self._http.request(
            method="GET",
            rest_url=self._credential.rest_url,
            endpoint="mobile/register/hebe",
            query={"mode": 2},
            pupil_id=pupil_id,
        )
        return [Account.model_validate(account) for account in envelope]

    async def get_exams(
        self,
        rest_url: str,
        pupil_id: int,
        date_from: date,
        date_to: date,
        last_sync_date: datetime = EPOCH_START_DATETIME,
        last_id: int = INT_MIN,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[Exam]:
        envelope = await self._http.request(
            method="GET",
            rest_url=rest_url,
            pupil_id=pupil_id,
            endpoint="mobile/exam/byPupil",
            query={
                "pupilId": pupil_id,
                "dateFrom": date_from,
                "dateTo": date_to,
                "lastSyncDate": last_sync_date,
                "lastId": last_id,
                "pageSize": page_size,
            },
        )
        return [Exam.model_validate(exam) for exam in envelope]

    async def get_homework(
        self,
        rest_url: str,
        pupil_id: int,
        date_from: date,
        date_to: date,
        last_sync_date: datetime = EPOCH_START_DATETIME,
        last_id: int = INT_MIN,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[Homework]:
        envelope = await self._http.request(
            method="GET",
            rest_url=rest_url,
            pupil_id=pupil_id,
            endpoint="mobile/homework/byPupil",
            query={
                "pupilId": pupil_id,
                "dateFrom": date_from,
                "dateTo": date_to,
                "lastSyncDate": last_sync_date,
                "lastId": last_id,
                "pageSize": page_size,
            },
        )
        return [Homework.model_validate(homework) for homework in envelope]

    async def get_schedule(
        self,
        rest_url: str,
        pupil_id: int,
        date_from: date,
        date_to: date,
        last_id: int = INT_MIN,
        page_size: int = DEFAULT_PAGE_SIZE,
        last_sync_date: datetime = EPOCH_START_DATETIME,
    ) -> list[Schedule]:
        envelope = await self._http.request(
            method="GET",
            rest_url=rest_url,
            pupil_id=pupil_id,
            endpoint="mobile/schedule/withchanges/byPupil",
            query={
                "pupilId": pupil_id,
                "dateFrom": date_from,
                "dateTo": date_to,
                "lastId": last_id,
                "pageSize": page_size,
                "lastSyncDate": last_sync_date,
            },
        )
        return [Schedule.model_validate(schedule) for schedule in envelope]
