from dataclasses import dataclass
from enum import Enum
from random import Random

from custom_types import LocalClockInfo, LocalEventSubTypes, LocalEventTypes, Severity, Area
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue

@dataclass
class AppPacket:
    payload: bytes


class AppState(Enum):
    INITIAL_SLEEP = 0
    SENSOR = 1
    FORWARDING = 2
    DEDUP = 3


class APP:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, app_to_dll_tx: list[AppPacket], dll_to_app_rx: list[AppPacket]):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.state = AppState.INITIAL_SLEEP
        self.random = Random(self.node_id)
        self.app_to_dll_tx = app_to_dll_tx
        self.dll_to_app_rx = dll_to_app_rx

    def tick(self, current_global_tick: int) -> None:
        match self.state:
            case AppState.INITIAL_SLEEP:
                # rnd = self.random.choices([0, 1, 3, 5], k=3)
                # rnd = int(sum(rnd) / 3)
                # sleep_ms = (45 + rnd) * 60 * 1000
                
                sleep_ms = 50 * 60 * 1000 # 50 min
                self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} will sleep {sleep_ms} ms before starting protocol")
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                self.state = AppState.SENSOR

            case AppState.SENSOR:
                # Simulate sensor data collection
                self.state = AppState.FORWARDING
                pass

            case AppState.FORWARDING:
                while self.dll_to_app_rx:
                    packet = self.dll_to_app_rx.pop(0)
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} APP received packet from DLL, payload length={len(packet.payload)}")
            

    def enqueue_payload(self, payload: bytes) -> None:
        self.app_to_dll_tx.append(AppPacket(payload=payload))

    def reset(self, current_global_tick: int) -> None:
        self.state = AppState.INITIAL_SLEEP 
        self.app_to_dll_tx.clear()
        self.dll_to_app_rx.clear()
        self.random = Random(self.node_id)
