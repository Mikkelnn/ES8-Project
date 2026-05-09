from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, List, Set

from crc import Calculator, Configuration

from Interfaces import IRSSI, ILength
from loraWanFrameHelper import LoRaWanPHYPayload
from payload_types import MegaSync, PayloadData, PayloadHopCnt

config = Configuration(
    width=16,
    polynomial=0x1021,
    init_value=0xFFFF,
    final_xor_value=0xFFFF,
    reverse_input=True,
    reverse_output=True,
)

calculator = Calculator(config, optimized=True)


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
    data: List[Any] = field(default_factory=list)


class LocalEventTypes(Enum):
    LOCAL_TIME = "LOCAL_TIME"
    SYNC_LOCAL_TIME = "SYNC_LOCAL_TIME"
    TRANCEIVER_STATUS = "TRANCEIVER_STATUS"
    TRANCEIVER_RECEIVED_DATA = "TRANCEIVER_RECEIVED_DATA"
    TRANCEIVER_TRANSMIT_DATA = "TRANCEIVER_TRANSMIT_DATA"
    TRANCEIVER_SET_STATE = "TRANCEIVER_SET_STATE"
    NODE_SLEEP_FOR = "NODE_SLEEP_FOR"
    NODE_SLEEP = "NODE_SLEEP"
    NODE_WAKE_UP = "NODE_WAKE_UP"
    SET_TIMER = "SET_TIMER"


class TransceiverState(Enum):
    IDLE = 0
    TRANSMITTING = 1
    RECEIVING = 2


class LocalEventSubTypes(str, Enum):
    TIMER_1 = "TIMER_1"
    TIMER_2 = "TIMER_2"


@dataclass
class NodeMediumInfo:
    position: tuple[int, int]
    neighbors: List[int]
    gateways_in_range: List[int]
    is_gateway: bool = False


@dataclass
class LogMessage:
    global_time: int
    severity: Severity
    area: Area
    info: str
    data: Any | None = None


class LoRaD2DFrameType(IntEnum):
    REQ_HOP_ACK = 0  # Request for hop count ACK, used by junction nodes to request ACK for a hop count
    CHANGE_HOP_COUNT = 1  # used by junction nodes to instruct other nodes to change thair hop count to the gateway, used when if multiple nodes have same hop count, they will be assigend a new uniuqe hop count ensuring no collisions.
    HOP_ACK = 2  # ACK for use hop count, used by junction nodes to ACK the count from a closer node
    DATA_FROM_GW = 3
    DATA_TO_GW = 4
    CURRENT_HOP_COUNT = 5  # sent as nodes hopcount changes and as idle packets to maintain updated hop count information in the network


@dataclass
class LoRaD2DFrame(ILength, IRSSI):
    source_node_id: int  # uint32
    destination_node_id: Set[int]  # uint32
    type: LoRaD2DFrameType  # uint8
    payload: PayloadData | PayloadHopCnt | MegaSync
    rssi: int = 0  # uint32
    crc: int = 0  # uint16
    # frame_count?
    # timestamp?
    # TTL?

    @property
    def length(self) -> int:
        # Source (4) + Destination (4 bytes per node) + Type (1) + Payload (Dynamic) + CRC (2)       (RSSI sent, but not counted, since IRL measured via radio, not in packet)
        return 4 + len(self.destination_node_id) * 4 + 1 + self.payload.length + 2

    def to_crc_bytes(self) -> bytes:
        data = bytearray()

        data += self.source_node_id.to_bytes(4, "big")

        for destination in sorted(self.destination_node_id):
            data += destination.to_bytes(4, "big")

        data += self.type.value.to_bytes(1, "big")

        data += self.payload.to_bytes()

        return bytes(data)

    def crc_calc(self) -> None:
        self.crc = calculator.checksum(self.to_crc_bytes())


@dataclass
class LocalClockInfo:
    current_local_time: int
    timer_1_remaining: int | None
    timer_2_remaining: int | None


@dataclass
class LocalEventNet:
    type: LocalEventTypes
    data: int | dict[MediumTypes, TransceiverState] | TransceiverState | LoRaWanPHYPayload | LoRaD2DFrame | LocalClockInfo
    sub_type: MediumTypes | LocalEventSubTypes | None = None
