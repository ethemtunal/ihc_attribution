from pydantic import BaseModel


class AttributionFailureEntity(BaseModel):
    conv_id: str
    session_id: str | None = None
    reason: str
    status_code: int | None = None
