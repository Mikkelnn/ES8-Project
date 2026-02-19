from pydantic import BaseModel, Field
from typing import List, Any
from enum import Enum

# Define allowed severities
class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# Define allowed areas
class Area(str, Enum):
    SIMULATOR = "SIMULATOR"
    NODE = "NODE"
    GATEWAY = "GATEWAY"
    EVENT = "EVENT"
    BATTERY = "BATTERY"
    CLOCK = "CLOCK"
    TRANCEIVER = "TRANCEIVER"
    OTHER = "OTHER"

class EventNet(BaseModel):
    node_id: int
    time_start: int
    time_end: int
    data: List[Any] = Field(default_factory=list)
    type: str