from pathlib import Path

from pydantic import BaseModel


class AttributionRunResult(BaseModel):
    success_path: Path
    failed_path: Path
    success_count: int
    failed_count: int
