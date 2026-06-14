from pydantic import BaseModel


class ChannelReportingEntity(BaseModel):
    channel_name: str
    date: str
    cost: float
    ihc: float
    ihc_revenue: float
