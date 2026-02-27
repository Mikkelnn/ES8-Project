from dataclasses import dataclass
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
    MEDIUM = "MEDIUM"
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
    LORA_D2D = "LORA_D2D"
    LORA_WAN = "LORA_WAN"

class TimeScales(float, Enum):
    MS = 0.001
    MUS = 0.000001
    NS = 0.000000001
    PS = 0.000000000001

@dataclass
class EventNet:
    node_id: int
    time_start: int
    time_end: int
    type: EventNetTypes
    type_medium: MediumTypes
    data: List[Any] = Field(default_factory=list)

class LocalEventTypes(Enum):
    LOCAL_TIME = "LOCAL_TIME"
    TRANCEIVER_STATUS = "TRANCEIVER_STATUS"
    TRANCEIVER_RECEIVED_DATA = "TRANCEIVER_RECEIVED_DATA"
    TRANCEIVER_TRANSMIT_DATA = "TRANCEIVER_TRANSMIT_DATA"
    TRANCEIVER_SET_STATE = "TRANCEIVER_SET_STATE"

class TranceiverState(Enum):
    IDLE = 0
    TRANSMITTING = 1
    RECEIVING = 2

class LocalEventSubTypes(str, Enum):
    Placeholder = "PLACEHOLDER" # This is a placeholder value, you can replace it with actual subtypes as needed

@dataclass
class LocalEventNet:
    type: LocalEventTypes
    data: int | dict[MediumTypes, TranceiverState] |TranceiverState | List[Any]
    sub_type: MediumTypes | LocalEventSubTypes | None = None

@dataclass
class NodeMediumInfo:
    position: tuple[int, int]
    neighbors: List[int]

@dataclass
class LogMessage:
    global_time: int
    severity: Severity
    area: Area
    info: str
    data: Any | None = None