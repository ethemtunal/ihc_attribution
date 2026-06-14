from pydantic import BaseModel


class SessionSourceEntity(BaseModel):
    session_id: str
    user_id: str
    event_date: str
    event_time: str
    channel_name: str
    holder_engagement: int
    closer_engagement: int
    impression_interaction: int
