from typing import List

from custom_types import LoRaWanPHYPayload, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, MediumTypes, TransceiverState, Severity, Area
from loraWanFrameHelper import make_uplink
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue


class WANDLL:
    def __init__(
        self,
        node_id: int,
        local_event_queue: LocalEventQueue,
        log: ILogger,
    ):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.hopcount_to_gateway = 65535
        self.tx_buffer: List[LoRaWanPHYPayload] = []
        self._waiting_for_ack = False
        self._connect_attempted = False

    def enqueue_payload(self, payload: bytes) -> None:
        self.tx_buffer.append(make_uplink(dev_addr=self.node_id, frame_count=0, payload=payload, confirmed=False))

    def tick(
        self,
        current_global_tick: int,
        current_local_clock_info: LocalClockInfo,
        current_transceiver_states: dict,
        current_receptions: list,
        wan_active: bool,
    ) -> None:
        if self.hopcount_to_gateway == 65535:
            self._run_gateway_connect(current_global_tick, current_local_clock_info, current_transceiver_states, current_receptions)
            return

        if wan_active:
            self._run_wan_forwarding(current_transceiver_states)

    def _run_gateway_connect(
        self,
        current_global_tick: int,
        current_local_clock_info: LocalClockInfo,
        current_transceiver_states: dict,
        current_receptions: list,
    ) -> None:
        if not self._connect_attempted:
            frame = make_uplink(dev_addr=self.node_id, frame_count=0, payload=b"", confirmed=True)
            self.local_event_queue.add_event_to_next_tick(
                type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA,
                sub_type=MediumTypes.LORA_WAN,
                data=frame,
            )
            self._connect_attempted = True
            self._waiting_for_ack = True
            self.log.add(
                Severity.DEBUG,
                Area.PROTOCOL,
                current_global_tick,
                f"Node {self.node_id} attempts gateway connect via WAN",
            )
            return

        if self._waiting_for_ack:
            if current_transceiver_states[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.SET_TIMER,
                    sub_type=LocalEventSubTypes.TIMER_1,
                    data=1000 - 10,
                )
                self._waiting_for_ack = False
                return

            timer_1 = current_local_clock_info.timer_1_remaining
            if timer_1 is not None and timer_1 <= 0:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_SET_STATE,
                    sub_type=MediumTypes.LORA_WAN,
                    data=TransceiverState.IDLE,
                )
                self._connect_attempted = False
                self.log.add(
                    Severity.INFO,
                    Area.PROTOCOL,
                    current_global_tick,
                    f"Node {self.node_id} failed gateway connect, will retry later",
                )
                return

            for reception in current_receptions:
                reception_data = reception.data
                if reception_data.mac_payload and reception_data.mac_payload.dev_addr == self.node_id and reception_data.is_ack():
                    self.hopcount_to_gateway = 0
                    self.local_event_queue.add_event_to_next_tick(
                        type=LocalEventTypes.TRANCEIVER_SET_STATE,
                        sub_type=MediumTypes.LORA_WAN,
                        data=TransceiverState.IDLE,
                    )
                    self.log.add(
                        Severity.INFO,
                        Area.PROTOCOL,
                        current_global_tick,
                        f"Node {self.node_id} connected directly to gateway via WAN",
                    )
                    self._waiting_for_ack = False
                    return

    def _run_wan_forwarding(self, current_transceiver_states: dict) -> None:
        if len(self.tx_buffer) == 0:
            return

        if current_transceiver_states[MediumTypes.LORA_WAN] != TransceiverState.TRANSMITTING:
            next_packet = self.tx_buffer.pop(0)
            self.local_event_queue.add_event_to_next_tick(
                type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA,
                sub_type=MediumTypes.LORA_WAN,
                data=next_packet,
            )
