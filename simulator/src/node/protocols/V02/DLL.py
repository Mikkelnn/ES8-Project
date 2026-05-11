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
        self.retain_depth_old_megasync = 20
        self._megasync_req_interval_ms = 60 * 60 * 1000  # 1 hour

        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.state = DLLState.DISCOVERY
        self.slot_period_counter = 0
        self.d2d_layer.reset(current_global_tick)
        self.wan_layer.reset(current_global_tick)
        self.current_period_start_time = None
        self.sync_buffer: list[MegaSync] = []
        self._last_megasync_req_local_time: int = 0
        self._megasync_req_due: bool = False

    def _remove_duplicates_from_buffers(self) -> None:
        """Remove duplicate frames across D2D and WAN buffers based on CRC/MIC. TX buffers kept, RX duplicates removed."""
        seen_checksums = set()

        for buffer_list in [self.d2d_layer._tx_buffer, self.wan_layer._tx_buffer, self.d2d_layer._rx_buffer, self.wan_layer._rx_buffer]:
            i = 0
            while i < len(buffer_list):
                frame = buffer_list[i]
                checksum = frame.crc if hasattr(frame, 'crc') else frame.mic

                if isinstance(checksum, bytes):
                    checksum = int.from_bytes(checksum, 'big')

                if checksum in seen_checksums:
                    buffer_list.pop(i)
                else:
                    seen_checksums.add(checksum)
                    i += 1

    def tick(self, current_global_tick: int) -> None:
        current_local_clock_info = cast(LocalClockInfo, self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)[0].data)

        self._remove_duplicates_from_buffers()

        # Determine if discovery have occured, otherwise start with WAN then D2D
        match self.state:
            case DLLState.DISCOVERY:
                if self.wan_layer.link_state == LinkState.DISCOVERING:
                    self.wan_layer.tick(current_global_tick, current_local_clock_info)
                elif self.wan_layer.link_state == LinkState.LINK_ESTABLISHED:
                    self.d2d_layer.set_has_gateway_link()
                    self.state = DLLState.FORWARDING
                elif self.wan_layer.link_state == LinkState.NO_LINK:
                    finished = self.d2d_layer.tick(current_global_tick, current_local_clock_info, self.slot_period_counter)
                    if finished and self.d2d_layer.link_established:
                        self.state = DLLState.FORWARDING
                        self.slot_period_counter = self.d2d_layer.slot_period_counter
                        self._increment_slot_period_counter()

                        sleep_ms = (current_local_clock_info.current_local_time - self.d2d_layer.estimated_period_start) + self.slot_period_ms  # ty: ignore[unsupported-operator]
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                        self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery with D2D route to gateway, sleeping until next slot period")

                    elif finished and not self.d2d_layer.link_established:
                        # sleep before retrying discovery
                        if self.d2d_layer.discovery_state in [DiscoverStates.WAIT_REQ_ACK_SENT, DiscoverStates.WAITING_FOR_ACK]:
                            sleep_ms = (current_local_clock_info.current_local_time - self.d2d_layer.estimated_period_start) + self.slot_period_ms  # ty: ignore[unsupported-operator]
                            if self.d2d_layer.slot_period_counter + 1 >= self.lora_wan_slot_interleave:
                                # sleep next period as it is LORA WAN -> no D2D
                                sleep_ms + self.slot_period_ms

                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery waiting for ACK, sleeping until next slot period to retry with D2D")
                        else:
                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=self.d2d_rety_period_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery without finding route, sleeping before retrying with D2D")

            case DLLState.FORWARDING:
                if self.current_period_start_time is None:
                    self.current_period_start_time = current_local_clock_info.current_local_time

                current_local_time = current_local_clock_info.current_local_time
                if abs(current_local_time - self._last_megasync_req_local_time) >= self._megasync_req_interval_ms:
                    self._megasync_req_due = True

                is_wan_slot = self.slot_period_counter == 0
                if self._megasync_req_due and self._effective_hopcount() == 0 and is_wan_slot:
                    self.wan_layer.enqueue_payload(MegaSyncReq())
                    self._last_megasync_req_local_time = current_local_time
                    self._megasync_req_due = False
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} sent periodic MegaSyncReq")

                finished = self.wan_layer.tick(current_global_tick, current_local_clock_info) if is_wan_slot else self.d2d_layer.tick(current_global_tick, current_local_clock_info, slot_period_counter=0)

                if finished:
                    if not is_wan_slot:
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SYNC_LOCAL_TIME, data=self.d2d_layer.estimated_period_correction)

                    sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time - self.current_period_start_time)
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                    self.current_period_start_time = None
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished {'WAN' if self.slot_period_counter == 0 else 'D2D'} forwarding period, sleeping until next slot period ({sleep_ms} ms)")
                    self._increment_slot_period_counter()

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
                        msg.local_rx_time = self._get_local_time()
                        self._megasync_handle(msg, current_global_tick)
                    elif isinstance(msg, PayloadData):
                        # Forward received payload: try WAN if have direct connection (hopcount 0), else D2D relay
                        if self._effective_hopcount() == 0:
                            self.wan_layer.enqueue_payload(msg)
                        else:
                            self.d2d_layer.enqueue_payload(msg)
                    else:
                        self.dll_to_app_rx.append(msg)

    def _effective_hopcount(self) -> int:
        return self.d2d_layer.hopcount_to_gateway

    def _increment_slot_period_counter(self) -> None:
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

        for old_msg in self.sync_buffer:
            if msg is old_msg:
                return
            else:
                self.sync_buffer.append(msg)

        diff = self.retain_depth_old_megasync - len(self.sync_buffer)

        if diff < 0:
            for _ in range(abs(diff)):
                self.sync_buffer.pop(0)

        # self._flush_tx_buffers(current_global_tick) #TODO or not TODO

        current_time = self._get_local_time()
        sync_time_diff = current_time - msg.time + msg.total_handle_time

        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SYNC_LOCAL_TIME, data=sync_time_diff)
        self.d2d_layer.enqueue_payload(msg)

        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} MegaSync sync time {current_time + sync_time_diff}")
