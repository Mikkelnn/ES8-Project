from enum import Enum
from typing import cast

from custom_types import Area, LocalClockInfo, LocalEventTypes, Severity
from logger.ILogger import ILogger
from loraWanFrameHelper import MACPayload
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.D2DDLL import D2DDLL, DiscoverStates
from node.protocols.V02.WANDLL import WANDLL, LinkState
from payload_types import MegaSync, MegaSyncReq, PayloadData


class DLLState(Enum):
    DISCOVERY = 0
    FORWARDING = 1


class DLL:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger, d2d_layer: D2DDLL, wan_layer: WANDLL, app_to_dll_tx: list[PayloadData | MegaSyncReq], dll_to_app_rx: list[MACPayload | PayloadData | MegaSync]):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick
        self.log = log
        self.d2d_layer: D2DDLL = d2d_layer
        self.wan_layer: WANDLL = wan_layer
        self.app_to_dll_tx = app_to_dll_tx
        self.dll_to_app_rx = dll_to_app_rx

        self.slot_period_ms = 60_000  # 1 min slot period
        self.lora_wan_slot_interleave = 60
        self.d2d_rety_period_ms = 25 * 60_000  # 25 min retry period for D2D allow battery to charge

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
                elif self.wan_layer.link_state == LinkState.LINK_ESTABLISHED:
                    self.d2d_layer.set_has_gateway_link()
                    self.state = DLLState.FORWARDING
                elif self.wan_layer.link_state == LinkState.NO_LINK:
                    finished = self.d2d_layer.tick(current_global_tick, current_local_clock_info)
                    if finished and self.d2d_layer.link_established:
                        self.state = DLLState.FORWARDING
                        sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time % self.slot_period_ms)  # TODO: do right...
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                        self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery with D2D route to gateway, sleeping until next slot period")

                    elif finished and not self.d2d_layer.link_established:
                        # sleep before retrying discovery
                        if self.d2d_layer.discovery_state in [DiscoverStates.WAIT_REQ_ACK_SENT, DiscoverStates.WAITING_FOR_ACK]:
                            sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time % self.slot_period_ms)  # TODO: do right...
                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery waiting for ACK, sleeping until next slot period to retry with D2D")
                        else:
                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=self.d2d_rety_period_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery without finding route, sleeping before retrying with D2D")

            case DLLState.FORWARDING:
                if self.current_period_start_time is None:
                    self.current_period_start_time = current_local_clock_info.current_local_time

                finished = False
                if self.slot_period_counter == 0:
                    finished = self.wan_layer.tick(current_global_tick, current_local_clock_info)
                else:
                    finished = self.d2d_layer.tick(current_global_tick, current_local_clock_info)

                if finished:
                    # sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time - self.current_period_start_time)
                    sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time % self.slot_period_ms)  # TODO: do right... use above but fix DISCOVERY sleep
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                    self.current_period_start_time = None
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished {'WAN' if self.slot_period_counter == 0 else 'D2D'} forwarding period, sleeping until next slot period ({sleep_ms} ms)")
                    self._increment_hop_count()

                self._route_app_packets(current_global_tick)

    def _route_app_packets(self, current_global_tick: int) -> None:
        while self.app_to_dll_tx:
            packet = self.app_to_dll_tx.pop(0)
            if self._effective_hopcount() == 0:
                self.wan_layer.enqueue_payload(packet)
            else:
                if isinstance(packet, PayloadData):
                    self.d2d_layer.enqueue_payload(packet)
                else:
                    self.log.add(Severity.ERROR, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} tried to enqueue MegaSyncReq, when not hopcount 0")

        while self.dll_to_app_rx:
            if self._effective_hopcount() == 0:
                queue = self.wan_layer.dequeue_payload()
                while queue:
                    msg = queue.pop(0)
                    if isinstance(msg.frm_payload, MegaSync):
                        self._megasync_handle(msg.frm_payload, current_global_tick)
                    else:
                        self.dll_to_app_rx.append(msg)
                d2d_queue = self.d2d_layer.dequeue_payload()
                while d2d_queue:
                    msg = d2d_queue.pop(0)
                    if isinstance(msg, PayloadData):
                        self.wan_layer.enqueue_payload(msg)
                    elif isinstance(msg, MegaSync):
                        self._megasync_handle(msg, current_global_tick)
            else:
                queue = self.d2d_layer.dequeue_payload()
                while queue:
                    msg = queue.pop(0)
                    if isinstance(msg, MegaSync):
                        self._megasync_handle(msg, current_global_tick)
                    elif isinstance(msg, PayloadData):
                        # Forward received payload: try WAN if have direct connection (hopcount 1->0), else D2D relay
                        has_lower_hopcount_neighbor = any(n.hopcount_to_gateway < self.d2d_layer.hopcount_to_gateway for n in self.d2d_layer.known_neighbors)
                        if self.d2d_layer.hopcount_to_gateway == 1 and has_lower_hopcount_neighbor:
                            self.wan_layer.enqueue_payload(msg)
                        else:
                            self.d2d_layer.enqueue_payload(msg)
                    else:
                        self.dll_to_app_rx.append(msg)

    def _effective_hopcount(self) -> int:
        return self.d2d_layer.hopcount_to_gateway

    def _increment_hop_count(self) -> None:
        self.slot_period_counter += 1
        if self.slot_period_counter >= self.lora_wan_slot_interleave:
            self.slot_period_counter = 0

    def _get_local_time(self) -> int:
        events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)
        if events:
            clock_info = cast(LocalClockInfo, events[0].data)
            return clock_info.current_local_time
        return 0

    def _flush_tx_buffers(self, current_global_tick: int) -> None:  # TODO, this must be able to handle that we cannot send all at once.
        while self.app_to_dll_tx:
            packet = self.app_to_dll_tx.pop(0)
            if self._effective_hopcount() == 0:
                self.wan_layer.enqueue_payload(packet)
            elif isinstance(packet, PayloadData):
                self.d2d_layer.enqueue_payload(packet)
            else:
                self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} flushed MegaSyncReq before clock sync")

    def _megasync_handle(self, msg: MegaSync, current_global_tick: int) -> None:
        self._flush_tx_buffers(current_global_tick)
        sync_time = msg.time + msg.total_handle_time
        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SYNC_LOCAL_TIME, data=sync_time)
        current_local = self._get_local_time()
        new_handle_time = msg.total_handle_time + max(0, current_local - msg.time)
        forwarded = MegaSync(time=msg.time, total_handle_time=new_handle_time)
        self.d2d_layer.enqueue_payload(forwarded)
        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} MegaSync sync: time={sync_time}, handle={new_handle_time}")
