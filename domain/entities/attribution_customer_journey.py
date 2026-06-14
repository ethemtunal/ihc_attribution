from pydantic import BaseModel


class AttributionCustomerJourneyEntity(BaseModel):
    conv_id: str
    session_id: str
    ihc: float
