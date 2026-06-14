from pydantic import BaseModel


class JourneyRowEntity(BaseModel):
    conv_id: str
    conv_user_id: str
    conv_date: str
    conv_time: str
    revenue: float
    session_id: str
    event_date: str
    event_time: str
    channel_name: str
    holder_engagement: int
    closer_engagement: int
    impression_interaction: int
