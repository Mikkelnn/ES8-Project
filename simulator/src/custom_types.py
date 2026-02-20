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

class EventNetTypes(str, Enum):
    CANCELED = "CANCELED"
    TRANSMIT = "TRANSMIT"

class MediumTypes(str, Enum):
    LORA = "LORA"
    LORAD2D = "LORAD2D"
    LORAWAN = "LORAWAN"
    

class EventNet(BaseModel):
    node_id: int
    time_start: int
    time_end: int
    data: List[Any] = Field(default_factory=list)
    type: EventNetTypes
    type_medium: MediumTypes



class LocalEventTypes(str, Enum):
    LOCAL_TIME = "LOCAL_TIME"
    TRANCEIVER_STATUS = "TRANCEIVER_STATUS"
    TRANCEIVER_RECEIVED_DATA = "TRANCEIVER_RECEIVED_DATA"
    TRANCEIVER_TRANSMIT_DATA = "TRANCEIVER_TRANSMIT_DATA"
    TRANCEIVER_SET_STATE = "TRANCEIVER_SET_STATE"

class LocalEventSubTypes(str, Enum):
    LORA_WAN = "LORA_WAN"
    LORA_D2D = "LORA_D2D"

class LocalEventNet(BaseModel):
    type: LocalEventTypes
    sub_type: LocalEventSubTypes | None = None
    data: Any