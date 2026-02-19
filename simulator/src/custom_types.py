from pydantic import BaseModel, Field
from typing import List, Any


class EventNet(BaseModel):
    node_id: int
    time_start: int
    time_end: int
    data: List[Any] = Field(default_factory=list)
    type: str