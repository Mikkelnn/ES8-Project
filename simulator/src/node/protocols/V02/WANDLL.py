from enum import Enum
from typing import List, cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaWanPHYPayload, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from loraWanFrameHelper import MACPayload, make_uplink
from node.event_local_queue import LocalEventQueue
from node.transceiver.lora_tx_duration_calculator import LoRaTxDurationCalculator
from payload_types import MegaSyncReq, PayloadData


class LinkState(Enum):
    DISCOVERING = 0
    NO_LINK = 1
    LINK_ESTABLISHED = 2


class TransmitState(Enum):
    IDLE = 0
    TRANSMITTING = 1
    TRANSMITTING_WAITING_FOR_RX = 2
    WAIT_RX = 3
    RX = 4


class WANDLL:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self._duration_calculator = LoRaTxDurationCalculator(second_to_global_tick=0.001)
        self.tx_counter = 0
        self.tx_one_go_tick_cap = 36_000
        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self._tx_buffer: List[LoRaWanPHYPayload] = []
        self._rx_buffer: List[LoRaWanPHYPayload] = []
        self._connect_attempted = False
        self.link_state = LinkState.DISCOVERING
        self.transmit_state = TransmitState.IDLE

    def enqueue_payload(self, payload: PayloadData) -> None:
        self._tx_buffer.append(make_uplink(dev_addr=self.node_id, frame_count=0, payload=payload, confirmed=False))

    def dequeue_payload(self) -> list[MACPayload]:
        queue = []
        while self._rx_buffer:
            queue.append(self._rx_buffer.pop(0).mac_payload)

        return queue

    def request_mega_sync(self) -> None:
        self._tx_buffer.append(make_uplink(dev_addr=self.node_id, frame_count=0, payload=MegaSyncReq(), confirmed=True))

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> bool:
        """Returns True if the current slot period is finished and we can move on to the next slot, False if we are still in the current slot period"""
        current_transceiver_states = cast(dict[MediumTypes, TransceiverState], self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data)

        match self.link_state:
            case LinkState.DISCOVERING:
                self._run_wan_forwarding(current_local_clock_info, current_transceiver_states)
                self._run_gateway_connect(current_global_tick)
                return False

            case LinkState.NO_LINK:
                return True  # discovery finished, but no link established, move on to D2D

            case LinkState.LINK_ESTABLISHED:
                return self._run_wan_forwarding(current_local_clock_info, current_transceiver_states)
                # maybe handle ACK in _rx_buffer -> use for re transmission and link state management?

        self.log.add(Severity.ERROR, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} tick match cases not hit for WANDLL, returning False")
        return False

    def _run_gateway_connect(self, current_global_tick: int) -> None:

        if self.transmit_state == TransmitState.IDLE and not self._connect_attempted:
            self.request_mega_sync()
            self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} attempts gateway connect via WAN")
            self._connect_attempted = True
            return

        if self._rx_buffer or self.transmit_state == TransmitState.IDLE:
            packet = self._rx_buffer.pop(0) if self._rx_buffer else None

            if packet and packet.is_ack():
                self.link_state = LinkState.LINK_ESTABLISHED
                self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} connected to gateway via WAN")
                return

            self.link_state = LinkState.NO_LINK
            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} failed to connect to gateway via WAN, moving on to D2D")

    def _run_wan_forwarding(self, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict[MediumTypes, TransceiverState]) -> bool:
        """Returns True if the current slot period is finished and we can move on to the next slot, False if we are still in the current slot period"""
        match self.transmit_state:
            case TransmitState.IDLE:
                if len(self._tx_buffer) == 0:
                    self.tx_counter = 0
                    return True  # nothing to transmit, period finished, can move on to next slot

                # TODO: handle max TX dutycycle and turn off tranceiver
                self.tx_counter += self._duration_calculator.get_duration(self._tx_buffer[0].length)
                if self.tx_counter >= self.tx_one_go_tick_cap:
                    self.tx_counter = 0
                    return True  # Too much tx time used

                next_packet = self._tx_buffer.pop(0)
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=next_packet)
                self.transmit_state = TransmitState.TRANSMITTING_WAITING_FOR_RX if next_packet.is_confirmed_uplink() else TransmitState.TRANSMITTING

            case TransmitState.TRANSMITTING:
                if current_transceiver_states[MediumTypes.LORA_WAN] != TransceiverState.TRANSMITTING:
                    self.transmit_state = TransmitState.IDLE

            case TransmitState.TRANSMITTING_WAITING_FOR_RX:
                if current_transceiver_states[MediumTypes.LORA_WAN] != TransceiverState.TRANSMITTING:
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, 0000000, f"Node {self.node_id} finished transmitting, waiting for ACK")
                    # timer until RX_1 slot
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=1000 - 10)
                    self.transmit_state = TransmitState.WAIT_RX

            case TransmitState.WAIT_RX:
                timer_1 = current_local_clock_info.timer_1_remaining
                if timer_1 is not None and timer_1 <= 0:
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, 0000000, f"Node {self.node_id} RX window open, waiting for ACK")
                    # timeout for RX windows + buffer
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=1000 + 10)
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)
                    self.transmit_state = TransmitState.RX

            case TransmitState.RX:
                current_reception = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_WAN)
                got_rx = False
                if current_reception:
                    reception_data = cast(LoRaWanPHYPayload, current_reception[0].data)
                    if reception_data.mac_payload and reception_data.mac_payload.dev_addr == self.node_id:
                        self._rx_buffer.append(reception_data)
                        got_rx = True

                timer_1 = current_local_clock_info.timer_1_remaining
                if (timer_1 is not None and timer_1 <= 0) or got_rx:
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
                    self.transmit_state = TransmitState.IDLE
                    return True  # transmission finished, can move on to next packet

        return False  # in progress
