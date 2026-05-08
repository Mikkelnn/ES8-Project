from enum import Enum
from random import Random

from custom_types import Area, LocalEventTypes, Severity
from logger.ILogger import ILogger
from loraWanFrameHelper import MACPayload
from node.event_local_queue import LocalEventQueue
from payload_types import PayloadData


class AppState(Enum):
    INITIAL_SLEEP = 0
    SENSOR = 1
    FORWARDING = 2
    DEDUP = 3


class APP:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, app_to_dll_tx: list[PayloadData], dll_to_app_rx: list[PayloadData | MACPayload]):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.state = AppState.INITIAL_SLEEP
        self.random = Random(self.node_id)
        self.app_to_dll_tx = app_to_dll_tx
        self.dll_to_app_rx = dll_to_app_rx
        self.payload_data = PayloadData(id={self.node_id})

    def tick(self, current_global_tick: int) -> None:
        match self.state:
            case AppState.INITIAL_SLEEP:
                # rnd = self.random.choices([0, 1, 3, 5], k=3)
                # rnd = int(sum(rnd) / 3)
                # sleep_ms = (45 + rnd) * 60 * 1000

                sleep_ms = 50 * 60 * 1000  # 50 min
                self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} will sleep {sleep_ms} ms before starting protocol")
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                self.state = AppState.SENSOR

            case AppState.SENSOR:
                self.state = AppState.FORWARDING
                self.payload_data.data.sensor1 = self.random.randint(0, 30)
                self.payload_data.data.sensor2 = self.random.randint(0, 30)
                self.payload_data.time = 0  # TODO set to local clock
                self.payload_data.length_calc()  # Now payload is ready to send

            case AppState.FORWARDING:
                while self.dll_to_app_rx:
                    packet = self.dll_to_app_rx.pop(0)
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} APP received packet from DLL, payload length={packet.length}")

    def enqueue_payload(self, payload: PayloadData) -> None:
        self.app_to_dll_tx.append(payload)

    def reset(self, current_global_tick: int) -> None:
        self.state = AppState.INITIAL_SLEEP
        self.app_to_dll_tx.clear()
        self.dll_to_app_rx.clear()
        self.random = Random(self.node_id)
