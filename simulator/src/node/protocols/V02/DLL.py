from enum import Enum
from typing import cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, Severity
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.D2DDLL import D2DDLL, DiscoverStates
from node.protocols.V02.WANDLL import WANDLL, LinkState
from payload_types import MegaSync, PayloadData


class DLLState(Enum):
    DISCOVERY = 0
    FORWARDING = 1


class DLL:
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger, d2d_layer: D2DDLL, wan_layer: WANDLL, app_to_dll_tx: list[PayloadData], dll_to_app_rx: list[PayloadData]):

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
        self._megasync_req_interval_ms = 2 * 60 * 60 * 1000  # 1 hour

        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.state = DLLState.DISCOVERY
        self.slot_period_counter = 0
        self.d2d_layer.reset(current_global_tick)
        self.wan_layer.reset(current_global_tick)
        self.current_period_start_time = None
        self.sync_buffer: set[int] = set() # all GPS times received
        self._last_megasync_req_local_time: int = 0
        self._megasync_req_due: bool = False

    def _remove_duplicates_from_buffers(self) -> None:
        """Remove duplicates: TX wins over RX. Also remove duplicate frames within RX buffers."""
        tx_checksums = set()

        for frame in self.d2d_layer._tx_buffer:
            checksum = frame.crc if hasattr(frame, "crc") else frame.mic
            if isinstance(checksum, bytes):
                checksum = int.from_bytes(checksum, "big")
            tx_checksums.add(checksum)

        for frame in self.wan_layer._tx_buffer:
            checksum = frame.crc if hasattr(frame, "crc") else frame.mic
            if isinstance(checksum, bytes):
                checksum = int.from_bytes(checksum, "big")
            tx_checksums.add(checksum)

        seen_rx = set()
        i = 0
        while i < len(self.d2d_layer._rx_buffer):
            frame = self.d2d_layer._rx_buffer[i]
            checksum = frame.crc if hasattr(frame, "crc") else frame.mic
            if isinstance(checksum, bytes):
                checksum = int.from_bytes(checksum, "big")

            payload_guid = "unknown"
            if hasattr(frame, "mac_payload") and hasattr(frame.mac_payload, "frm_payload") and hasattr(frame.mac_payload.frm_payload, "guid"):
                payload_guid = frame.mac_payload.frm_payload.guid
            elif hasattr(frame, "payload") and hasattr(frame.payload, "guid"):
                payload_guid = frame.payload.guid

            if checksum in tx_checksums:
                self.log.add(Severity.DEBUG, Area.PROTOCOL, 0, f"Node {self.node_id} duplicate removed GUID={payload_guid} from d2d_rx (in TX buffer)")
                self.d2d_layer._rx_buffer.pop(i)
            elif checksum in seen_rx:
                self.log.add(Severity.DEBUG, Area.PROTOCOL, 0, f"Node {self.node_id} duplicate removed GUID={payload_guid} from d2d_rx (duplicate in RX)")
                self.d2d_layer._rx_buffer.pop(i)
            else:
                seen_rx.add(checksum)
                i += 1

        seen_rx = set()
        i = 0
        while i < len(self.wan_layer._rx_buffer):
            frame = self.wan_layer._rx_buffer[i]
            checksum = frame.crc if hasattr(frame, "crc") else frame.mic
            if isinstance(checksum, bytes):
                checksum = int.from_bytes(checksum, "big")

            payload_guid = "unknown"
            if hasattr(frame, "mac_payload") and hasattr(frame.mac_payload, "frm_payload") and hasattr(frame.mac_payload.frm_payload, "guid"):
                payload_guid = frame.mac_payload.frm_payload.guid
            elif hasattr(frame, "payload") and hasattr(frame.payload, "guid"):
                payload_guid = frame.payload.guid

            if checksum in tx_checksums:
                self.log.add(Severity.DEBUG, Area.PROTOCOL, 0, f"Node {self.node_id} duplicate removed GUID={payload_guid} from wan_rx (in TX buffer)")
                self.wan_layer._rx_buffer.pop(i)
            elif checksum in seen_rx:
                self.log.add(Severity.DEBUG, Area.PROTOCOL, 0, f"Node {self.node_id} duplicate removed GUID={payload_guid} from wan_rx (duplicate in RX)")
                self.wan_layer._rx_buffer.pop(i)
            else:
                seen_rx.add(checksum)
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

                        sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time - self.d2d_layer.estimated_period_start)  # ty: ignore[unsupported-operator]
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                        self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery with D2D route to gateway, period counter {self.slot_period_counter}, sleeping until next slot period for {sleep_ms} ms")
                    elif finished and not self.d2d_layer.link_established:
                        # sleep before retrying discovery
                        if self.d2d_layer.discovery_state in [DiscoverStates.WAIT_REQ_ACK_SENT, DiscoverStates.WAITING_FOR_ACK]:
                            # print(f"node id: {self.node_id} estimated start: {self.d2d_layer.estimated_period_start}, ago: {(current_local_clock_info.current_local_time - self.d2d_layer.estimated_period_start)}")
                            sleep_ms = self.slot_period_ms - (current_local_clock_info.current_local_time - self.d2d_layer.estimated_period_start)  # ty: ignore[unsupported-operator]
                            self.d2d_layer.slot_period_counter += 1
                            if self.d2d_layer.slot_period_counter >= self.lora_wan_slot_interleave:
                                self.d2d_layer.slot_period_counter = 1  # set to one as WAN has completed after sleep
                                # sleep next period as it is LORA WAN -> no D2D
                                sleep_ms += self.slot_period_ms

                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery waiting for ACK, period counter: {self.d2d_layer.slot_period_counter}, sleeping until next slot period to retry with D2D for {sleep_ms} ms")
                        else:
                            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=self.d2d_rety_period_ms)
                            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished discovery without finding route, sleeping before retrying with D2D for {self.d2d_rety_period_ms} ms")

            case DLLState.FORWARDING:
                if self.current_period_start_time is None:
                    self.current_period_start_time = current_local_clock_info.current_local_time

                current_local_time = current_local_clock_info.current_local_time

                is_wan_slot = self.slot_period_counter == 0
                if self._have_direct_wan_connection() and is_wan_slot and abs(current_local_time - self._last_megasync_req_local_time) >= self._megasync_req_interval_ms:
                    self.wan_layer.request_mega_sync()
                    self._last_megasync_req_local_time = current_local_time
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} sent periodic MegaSyncReq")

                finished = self.wan_layer.tick(current_global_tick, current_local_clock_info) if is_wan_slot else self.d2d_layer.tick(current_global_tick, current_local_clock_info, slot_period_counter=self.slot_period_counter)

                if finished:
                    if not is_wan_slot:
                        sub_type = LocalEventSubTypes.MEGA_SYNC if self.d2d_layer.has_mega_sync else LocalEventSubTypes.MINI_SYNC
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SYNC_LOCAL_TIME, sub_type=sub_type, data=self.d2d_layer.estimated_period_correction)

                    sleep_ms = self.slot_period_ms - (current_local_time - self.current_period_start_time)
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, data=sleep_ms)
                    self.current_period_start_time = None
                    self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished {'WAN' if is_wan_slot else 'D2D'} forwarding period, slot period count: {self.slot_period_counter}, sleeping until next slot period ({sleep_ms} ms)")
                    self._increment_slot_period_counter()

                self._route_app_packets(current_global_tick)

    def _route_app_packets(self, current_global_tick: int) -> None:
        while self.app_to_dll_tx:
            packet = self.app_to_dll_tx.pop(0)
            if self._have_direct_wan_connection():
                self.wan_layer.enqueue_payload(packet)
            else:
                self.d2d_layer.enqueue_payload(packet)

        queue = self.wan_layer.dequeue_payload()
        while queue:
            msg = queue.pop(0)
            if isinstance(msg.frm_payload, MegaSync):
                self._megasync_handle(msg.frm_payload)
            else:
                pass  # we currently have no payloads from WAN that should be passed to APP-layer
                # self.dll_to_app_rx.append(msg)

        d2d_queue = self.d2d_layer.dequeue_payload()
        while d2d_queue:
            msg = d2d_queue.pop(0)
            if isinstance(msg, PayloadData):
                self.dll_to_app_rx.append(msg)
            elif isinstance(msg, MegaSync):  # we route directly back to tx
                self._megasync_handle(msg)

    def _have_direct_wan_connection(self) -> bool:
        return self.d2d_layer.hopcount_to_gateway == 0

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

    def _megasync_handle(self, msg: MegaSync) -> None:
        # TODO: maybe use GUIDs for this check, if memory ref is an issue
        # for old_time in self.sync_buffer:
        #     if msg.time == old_time:
        #         return

        if msg.time in self.sync_buffer:
            return

        self.sync_buffer.add(msg.time)
        self.d2d_layer.enqueue_payload(msg)

        # cap clean buffer
        while len(self.sync_buffer) > self.retain_depth_old_megasync:            
            self.sync_buffer.pop(0)
