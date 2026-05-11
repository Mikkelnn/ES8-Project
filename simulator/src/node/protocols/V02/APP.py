from enum import Enum
from random import Random
from typing import cast

from custom_types import Area, LocalClockInfo, LocalEventTypes, Severity
from logger.ILogger import ILogger
from loraWanFrameHelper import MACPayload
from node.event_local_queue import LocalEventQueue
from payload_types import PayloadData


class AppState(Enum):
    INITIAL_SLEEP = 0
    SENSOR = 1
    MEASURING = 2
    FORWARDING = 3
    DEDUP = 4


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
        self.sensor_buffer: list[tuple[int, int]] = []
        self.measurement_interval_ms = 3_600_000
        self.required_samples = 12
        self.last_measurement_time: int | None = None

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
                current_local_time = self._get_local_time()
                s1 = self.random.randint(0, 30)
                s2 = self.random.randint(0, 30)
                self.sensor_buffer.append((s1, s2))
                self.last_measurement_time = current_local_time
                self.state = AppState.MEASURING
                self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} first sensor measurement: s1={s1}, s2={s2}, entering MEASURING state")

            case AppState.MEASURING:
                current_local_time = self._get_local_time()
                if self.last_measurement_time is None:
                    return
                time_since_last = abs(current_local_time - self.last_measurement_time)
                if time_since_last >= self.measurement_interval_ms:
                    s1 = self.random.randint(0, 30)
                    s2 = self.random.randint(0, 30)
                    self.sensor_buffer.append((s1, s2))
                    self.last_measurement_time = current_local_time
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} measurement {len(self.sensor_buffer)}/12: s1={s1}, s2={s2}")
                    if len(self.sensor_buffer) == self.required_samples:
                        avg_s1 = sum(s[0] for s in self.sensor_buffer) // self.required_samples
                        avg_s2 = sum(s[1] for s in self.sensor_buffer) // self.required_samples
                        self.payload_data.data.sensor1 = avg_s1
                        self.payload_data.data.sensor2 = avg_s2
                        self.payload_data.time = float(current_local_time)
                        self.payload_data.length_calc()
                        self.enqueue_payload(self.payload_data)
                        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} enqueued averaged payload: avg_s1={avg_s1}, avg_s2={avg_s2}, GUID={self.payload_data.guid}")
                        self.sensor_buffer.clear()

            case AppState.FORWARDING:
                while self.dll_to_app_rx:
                    packet = self.dll_to_app_rx.pop(0)
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} APP received packet from DLL, payload length={packet.length}")

    def enqueue_payload(self, payload: PayloadData) -> None:
        self.app_to_dll_tx.append(payload)

    def _get_local_time(self) -> int:
        events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)
        if events:
            clock_info = cast(LocalClockInfo, events[0].data)
            return clock_info.current_local_time
        return 0

    def reset(self, current_global_tick: int) -> None:
        self.state = AppState.INITIAL_SLEEP
        self.app_to_dll_tx.clear()
        self.dll_to_app_rx.clear()
        self.random = Random(self.node_id)
        self.sensor_buffer.clear()
        self.last_measurement_time = None
