from pydantic import BaseModel


class JourneyTouchpointEntity(BaseModel):
    session_id: str
    timestamp: str
    channel: str
    holder_engagement: int
    closer_engagement: int
    impression_interaction: int
