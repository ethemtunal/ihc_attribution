from pydantic import BaseModel


class ConversionEntity(BaseModel):
    conv_id: str
    user_id: str
    conv_date: str
    conv_time: str
    revenue: float
