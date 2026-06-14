from pydantic import BaseModel

from domain.entities.journey_touchpoint import JourneyTouchpointEntity


class CustomerJourneyEntity(BaseModel):
    conversion_id: str
    conv_date: str
    conv_time: str
    revenue: float
    user_id: str
    sessions: list[JourneyTouchpointEntity]
