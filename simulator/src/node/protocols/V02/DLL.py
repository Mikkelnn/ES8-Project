from enum import Enum
from typing import Any

from custom_types import LocalClockInfo, LocalEventSubTypes, LocalEventTypes, MediumTypes, TransceiverState, Severity, Area
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.APP import AppPacket
from node.protocols.V02.D2DDLL import D2DDLL
from node.protocols.V02.WANDLL import WANDLL


class ProtocolState(Enum):
    DISCOVERY = 0
    FORWARDING = 1


class DLL:
    def __init__(
        self,
        node_id: int,
        local_event_queue: LocalEventQueue,
        second_to_global_tick: float,
        log: ILogger,
        d2d_layer: D2DDLL,
        wan_layer: WANDLL,
        app_to_dll_tx: list[AppPacket],
        dll_to_app_rx: list[AppPacket],
    ):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick
        self.log = log
        self.d2d_layer = d2d_layer
        self.wan_layer = wan_layer
        self.app_to_dll_tx = app_to_dll_tx
        self.dll_to_app_rx = dll_to_app_rx

        self.slot_period = 60_000
        self.slot_duration = 100
        self.slot_count = 5
        self.lora_wan_slot_interleave = 60

        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.state = ProtocolState.DISCOVERY
        self.next_state = ProtocolState.DISCOVERY
        self.current_slot = -1
        self.slot_period_counter = 0
        self.d2d_layer.reset(current_global_tick)
        self.wan_layer.reset(current_global_tick)

    def tick(self, current_global_tick: int) -> None:
        self._route_app_packets()

        current_local_clock_info = self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)[0].data
        current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data
        d2d_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_D2D)
        wan_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_WAN)

        self.gw_hopcount = self._effective_hopcount()
        self._advance_slot(current_local_clock_info)

        d2d_slot_active = self._is_d2d_slot_active()
        tx_slot = self._is_tx_slot()
        wan_active = self._is_wan_active()

        self.d2d_layer.tick(
            current_global_tick=current_global_tick,
            current_local_clock_info=current_local_clock_info,
            current_transceiver_states=current_transceiver_states,
            current_receptions=d2d_receptions,
            is_d2d_slot=d2d_slot_active,
            is_tx_slot=tx_slot and not wan_active,
        )

        self.wan_layer.tick(
            current_global_tick=current_global_tick,
            current_local_clock_info=current_local_clock_info,
            current_transceiver_states=current_transceiver_states,
            current_receptions=wan_receptions,
            wan_active=wan_active,
        )

        if self.gw_hopcount < 65535:
            self.state = ProtocolState.FORWARDING

    def _route_app_packets(self) -> None:
        while self.app_to_dll_tx:
            packet = self.app_to_dll_tx.pop(0)
            if self._effective_hopcount() == 0:
                self.wan_layer.enqueue_payload(packet.payload)
            else:
                self.d2d_layer.enqueue_payload(packet.payload)

    def _effective_hopcount(self) -> int:
        if self.wan_layer.hopcount_to_gateway == 0:
            return 0
        return min(self.d2d_layer.hopcount_to_gateway, self.wan_layer.hopcount_to_gateway)

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> None:
        if current_local_clock_info.timer_1_remaining is None or current_local_clock_info.timer_1_remaining == 0:
            self.current_slot += 1
            if self.current_slot < self.slot_count:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.SET_TIMER,
                    sub_type=LocalEventSubTypes.TIMER_1,
                    data=self.slot_duration,
                )
                if self.current_slot == self._tx_slot_index():
                    self.local_event_queue.add_event_to_next_tick(
                        type=LocalEventTypes.SET_TIMER,
                        sub_type=LocalEventSubTypes.TIMER_2,
                        data=10,
                    )
            else:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_SET_STATE,
                    sub_type=MediumTypes.LORA_D2D,
                    data=TransceiverState.IDLE,
                )
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_SET_STATE,
                    sub_type=MediumTypes.LORA_WAN,
                    data=TransceiverState.IDLE,
                )
                self.current_slot = -1
                self.slot_period_counter += 1
                if self.slot_period_counter >= self.lora_wan_slot_interleave:
                    self.slot_period_counter = 0
                sleep_ms = self.slot_period - self.slot_count * self.slot_duration
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.NODE_SLEEP_FOR,
                    data=sleep_ms,
                )

    def _tx_slot_index(self) -> int:
        return self._effective_hopcount() % self.slot_count if self._effective_hopcount() < 65535 else 0

    def _is_d2d_slot_active(self) -> bool:
        return self.current_slot >= 0 and self.current_slot < self.slot_count

    def _is_wan_active(self) -> bool:
        return self._effective_hopcount() == 0 and self.slot_period_counter == 0

    def _is_tx_slot(self) -> bool:
        return self.current_slot == self._tx_slot_index()
