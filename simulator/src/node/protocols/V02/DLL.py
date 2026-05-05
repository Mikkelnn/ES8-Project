from enum import Enum
from re import match
from typing import Any, cast
from unittest import case

from custom_types import LocalClockInfo, LocalEventSubTypes, LocalEventTypes, MediumTypes, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.APP import AppPacket
from node.protocols.V02.D2DDLL import D2DDLL
from node.protocols.V02.WANDLL import WANDLL, LinkState


class DLLState(Enum):
    DISCOVERY = 0    
    FORWARDING = 1

class DLL:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger,
        d2d_layer: D2DDLL, wan_layer: WANDLL, app_to_dll_tx: list[AppPacket], dll_to_app_rx: list[AppPacket]):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick
        self.log = log
        self.d2d_layer: D2DDLL = d2d_layer
        self.wan_layer: WANDLL = wan_layer
        self.app_to_dll_tx = app_to_dll_tx
        self.dll_to_app_rx = dll_to_app_rx

        self.slot_period_ms = 60_000
        self.lora_wan_slot_interleave = 60

        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.state = DLLState.DISCOVERY
        self.slot_period_counter = 0
        self.d2d_layer.reset(current_global_tick)
        self.wan_layer.reset(current_global_tick)
        self.current_period_start_time = None

    def tick(self, current_global_tick: int) -> None:
        current_local_clock_info = cast(LocalClockInfo, self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)[0].data)

        # Determine if discovery have occured, otherwise start with WAN then D2D
        match self.state:
            case DLLState.DISCOVERY:
                if self.wan_layer.link_state == LinkState.DISCOVERING:
                    self.wan_layer.tick(current_global_tick, current_local_clock_info)
                elif self.wan_layer.link_state == LinkState.NO_LINK:
                    finished = self.d2d_layer.tick(current_global_tick, current_local_clock_info)
                    if finished: # TODO: we should handel retry and not just move to forwarding, but for now we just move on
                        self.state = DLLState.FORWARDING
            
                # do sleep?

            case DLLState.FORWARDING:
                self._route_app_packets()

                if self.current_period_start_time is None:
                    self.current_period_start_time = current_local_clock_info.current_local_time

                finished = False
                if self.slot_period_counter == 0:
                    finished = self.wan_layer.tick(current_global_tick, current_local_clock_info)
                else:
                    finished = self.d2d_layer.tick(current_global_tick, current_local_clock_info)

                if finished:
                    self._increment_hop_count()
                    sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time - self.current_period_start_time)
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
       

    def _route_app_packets(self) -> None:
        while self.app_to_dll_tx:
            packet = self.app_to_dll_tx.pop(0)
            if self._effective_hopcount() == 0:
                self.wan_layer.enqueue_payload(packet.payload)
            else:
                self.d2d_layer.enqueue_payload(packet.payload)

    def _effective_hopcount(self) -> int:
        return 0 if self.wan_layer.link_established else self.d2d_layer.hopcount_to_gateway

    def _increment_hop_count(self) -> None:
        self.slot_period_counter += 1
        if self.slot_period_counter >= self.lora_wan_slot_interleave:
            self.slot_period_counter = 0
