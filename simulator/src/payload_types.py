import uuid
from dataclasses import dataclass, field
from typing import Set
from uuid import UUID

from crc import Calculator, Configuration

from Interfaces import ILength

config = Configuration(
    width=16,
    polynomial=0x1021,
    init_value=0xFFFF,
    final_xor_value=0xFFFF,
    reverse_input=True,
    reverse_output=True,
)

calculator = Calculator(config, optimized=True)


@dataclass
class Data(ILength):
    @property
    def length(self) -> int:
        return 2 + 2

    def to_bytes(self) -> bytes:
        return self.sensor1.to_bytes(2, "big", signed=False) + self.sensor2.to_bytes(2, "big", signed=False)

    sensor1: int = 0
    sensor2: int = 0


@dataclass
class PayloadData(ILength):
    id: Set[int]
    length_payload: int = 0
    time: float = 0.0
    data: Data = field(default_factory=Data)
    guid: UUID = field(default_factory=uuid.uuid4)

    @property
    def length(self) -> int:
        return 2 + len(self.id) * 4 + 4 + self.data.length

    def length_calc(self):
        self.length_payload = 2 + len(self.id) * 4 + 4 + self.data.length

    def to_bytes(self) -> bytes:
        id_bytes = b"".join(int(item).to_bytes(4, "big", signed=False) for item in sorted(self.id))
        return self.length_payload.to_bytes(2, "big", signed=False) + id_bytes + int(self.time).to_bytes(4, "big", signed=False) + self.data.to_bytes()


@dataclass
class PayloadHopCntSimple(ILength):
    """Simple hop count payload for REQ_HOP_ACK frames - only cnt (2 bytes total)"""

    cnt: int  # uint16

    @property
    def length(self) -> int:
        return 2

    def to_bytes(self) -> bytes:
        return self.cnt.to_bytes(2, "big", signed=False)


@dataclass
class PayloadHopCntMid(ILength):
    """Mid hop count payload for CHANGE_HOP_COUNT ACK responses - cnt and slot (3 bytes total)"""

    cnt: int  # uint16
    use_slot: int  # uint8
    slot_period_counter: int  # uint8

    @property
    def length(self) -> int:
        return 2 + 1 + 1

    def to_bytes(self) -> bytes:
        return self.cnt.to_bytes(2, "big", signed=False) + self.use_slot.to_bytes(1, "big", signed=False) + self.slot_period_counter.to_bytes(1, "big", signed=False)


@dataclass
class PayloadHopCntFull(ILength):
    """Full hop count payload for CURRENT_HOP_COUNT and REDISCOVER frames (8 bytes total)"""

    cnt: int  # uint16
    slot_period_counter: int  # uint8
    use_slot: int  # uint8
    time_offset_from_period_start: int  # uint16

    @property
    def length(self) -> int:
        return 2 + 1 + 1 + 2

    def to_bytes(self) -> bytes:
        return self.cnt.to_bytes(2, "big", signed=False) + self.slot_period_counter.to_bytes(1, "big", signed=False) + self.use_slot.to_bytes(1, "big", signed=False) + self.time_offset_from_period_start.to_bytes(2, "big", signed=False)


@dataclass
class MegaSync:
    guid: UUID = field(default_factory=uuid.uuid4)
    time: int = 0
    total_handle_time: int = 0
    local_rx_time: int = 0

    @property
    def length(self) -> int:
        return 8 + 4

    def to_bytes(self) -> bytes:
        return self.time.to_bytes(8, "big", signed=False) + self.total_handle_time.to_bytes(4, "big", signed=False)


@dataclass
class MegaSyncReq:
    guid: UUID = field(default_factory=uuid.uuid4)
    data: int = 1

    @property
    def length(self) -> int:
        return 1

    def to_bytes(self) -> bytes:
        return self.data.to_bytes(1, "big", signed=False)
