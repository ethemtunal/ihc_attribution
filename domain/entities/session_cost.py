from pydantic import BaseModel


class SessionCostEntity(BaseModel):
    session_id: str
    cost: float | None
