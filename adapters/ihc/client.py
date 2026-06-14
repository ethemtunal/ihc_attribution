import requests
from pydantic import BaseModel, ConfigDict, Field

from domain.entities.customer_journey import CustomerJourneyEntity
from domain.entities.journey_touchpoint import JourneyTouchpointEntity


class IhcSessionRequest(BaseModel):
    conversion_id: str
    session_id: str
    timestamp: str
    channel_label: str
    holder_engagement: int
    closer_engagement: int
    conversion: int
    impression_interaction: int = 0


class IhcSessionResult(BaseModel):
    conversion_id: str
    session_id: str
    initializer: float
    holder: float
    closer: float
    ihc: float


class IhcErrorTrigger(BaseModel):
    conversion_id: str
    session_id: str


class IhcPartialFailureError(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trigger: IhcErrorTrigger
    reason: str
    status_code: int = Field(alias="statusCode")


class IhcComputeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status_code: int = Field(alias="statusCode")
    value: list[IhcSessionResult]
    partial_failure_errors: list[IhcPartialFailureError] = Field(
        alias="partialFailureErrors"
    )


class IhcApiError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"IHC API returned {status_code}: {body}")


class IhcClient:
    """Thin HTTP wrapper around the IHC Attribution compute_ihc endpoint.

    Accepts our domain CustomerJourneyEntity objects, flattens them to the
    API's session-list shape, POSTs, and returns a typed response. The
    caller is responsible for chunking journeys so that each call respects
    the IHC limits (<=100 journeys AND <=3000 sessions per request).
    """

    COMPUTE_PATH = "/v1/compute_ihc"

    def __init__(
        self,
        api_key: str,
        conv_type_id: str,
        base_url: str = "https://api.ihc-attribution.com",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.conv_type_id = conv_type_id
        self.base_url = base_url
        self.timeout = timeout

    def compute(
        self,
        journeys: list[CustomerJourneyEntity],
        redistribution_parameter: dict[str, str | float | list[str]] | None = None,
    ) -> IhcComputeResponse:
        sessions = [
            self._to_ihc_session(t, j.conversion_id)
            for j in journeys
            for t in j.sessions
        ]
        body = {"customer_journeys": [s.model_dump() for s in sessions]}

        if redistribution_parameter:
            body["redistribution_parameter"] = redistribution_parameter  # type: ignore

        response = requests.post(
            f"{self.base_url}{self.COMPUTE_PATH}",
            params={"conv_type_id": self.conv_type_id},
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout,
        )
        if response.status_code not in (200, 206):
            raise IhcApiError(response.status_code, response.text)
        return IhcComputeResponse.model_validate(response.json())

    @staticmethod
    def _to_ihc_session(
        touchpoint: JourneyTouchpointEntity, conversion_id: str
    ) -> IhcSessionRequest:
        return IhcSessionRequest(
            conversion_id=conversion_id,
            session_id=touchpoint.session_id,
            timestamp=touchpoint.timestamp.replace("T", " "),
            channel_label=touchpoint.channel,
            holder_engagement=touchpoint.holder_engagement,
            closer_engagement=touchpoint.closer_engagement,
            conversion=0,
            impression_interaction=touchpoint.impression_interaction,
        )
