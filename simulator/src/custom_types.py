from dataclasses import dataclass
from pydantic import Field
from typing import List, Any
from enum import Enum

from loraWanFrameHelper import LoRaWanPHYPayload
from Interfaces import ILength

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
    PROTOCOL = "PROTOCOL"
    OTHER = "OTHER"

class SimState(Enum):
    """Simulation state tracking"""
    STOPPED = 0
    RUNNING = 1
    PAUSED = 2

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
    NODE_SLEEP_FOR = "NODE_SLEEP_FOR"
    NODE_SLEEP = "NODE_SLEEP"
    NODE_WAKE_UP = "NODE_WAKE_UP"

class TransceiverState(Enum):
    IDLE = 0
    TRANSMITTING = 1
    RECEIVING = 2

class LocalEventSubTypes(str, Enum):
    Placeholder = "PLACEHOLDER" # This is a placeholder value, you can replace it with actual subtypes as needed

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

class LoRaD2DFrameType(Enum):
    DATA_TO_GW = 0 
    HOP_COUNT_UPDATED = 1 # sent as nodes hopcount changes and as idle packets to maintain updated hop count information in the network
    CHANGE_HOP_COUNT = 2 # used by junction nodes to instruct other nodes to change thair hop count to the gateway, used when if multiple nodes have same hop count, they will be assigend a new uniuqe hop count ensuring no collisions.

@dataclass
class LoRaD2DFrame(ILength):
    source_node_id: int # uint32
    destination_node_id: int # uint32
    type: LoRaD2DFrameType # uint8    
    payload: List[Any]
    crc: int # uint16
    # frame_count?
    # timestamp?
    # TTL?

    @property
    def length(self) -> int:
        # Source (4) + Destination (4) + Type (1) + Payload + CRC (2)
        return 4 + 4 + 1 + len(self.payload) + 2

@dataclass
class LocalEventNet:
    type: LocalEventTypes
    data: int | dict[MediumTypes, TransceiverState] | TransceiverState | LoRaWanPHYPayload | LoRaD2DFrame
    sub_type: MediumTypes | LocalEventSubTypes | None = None
