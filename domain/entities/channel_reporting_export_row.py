from pydantic import BaseModel, Field


class ChannelReportingExportRow(BaseModel):
    channel_name: str
    date: str
    cost: float
    ihc: float
    ihc_revenue: float
    cpo: float | None = Field(default=None, serialization_alias="CPO")
    roas: float | None = Field(default=None, serialization_alias="ROAS")
