import statistics
from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import List, cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaD2DFrame, LoRaD2DFrameType, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.transceiver.lora_tx_duration_calculator import LoRaTxDurationCalculator
from payload_types import MegaSync, PayloadData, PayloadHopCntFull, PayloadHopCntMid, PayloadHopCntSimple


@dataclass
class D2DNeighborInfo:
    neighbor_id: int
    hopcount_to_gateway: int
    last_seen: int
    last_rssi: int
    in_slot: int
    first_tx_start_time_in_period: int


class DiscoverStates(Enum):
    NOT_DISCOVERED = 0
    LISTENING = 1
    REQ_ACK = 2
    WAITING_FOR_ACK = 3
    DISCOVERED = 4
    WAIT_REQ_ACK_SENT = 5


class D2DDLL:
    DISCOVERY_TIMEOUT_MS = (60 + 10) * 1000
    NEIGHBOR_DEAD_THREASHHOLD_MS = 120_000
    MAX_HOPCOUNT = 65535

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, slot_duration: int = 110, slot_count: int = 18):

        self._node_id = node_id
        self._local_event_queue = local_event_queue
        self._log = log
        self._slot_duration = slot_duration
        self._slot_count = slot_count
        self._mini_slot_count: int = 3
        self._duration_calculator = LoRaTxDurationCalculator(second_to_global_tick=0.001)  # in ms
        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.discovery_state = DiscoverStates.NOT_DISCOVERED
        self.hopcount_to_gateway = self.MAX_HOPCOUNT
        self.estimated_period_start = None
        self.slot_period_counter: int = 0
        self.estimated_period_correction: int = 0

        self._known_neighbors: List[D2DNeighborInfo] = []
        self._observed_slots: dict[int, int] = {}  # nodeID -> slot, tracks all visible nodes
        self._tx_buffer: List[LoRaD2DFrame] = []
        self._rx_buffer: List[LoRaD2DFrame] = []
        self._current_slot: int = -1
        self._own_tx_slot: int = 0  # used for REQ_ACK
        self._offset_for_req_ack: int = 0
        self._tx_start_end_buffer: int = 10
        self._tx_offset_done = False
        self._rnd = Random(self._node_id)
        self._slot_period_start: int = 0

    @property
    def link_established(self) -> bool:
        return self.hopcount_to_gateway < self.MAX_HOPCOUNT and self.discovery_state == DiscoverStates.DISCOVERED

    @property
    def _period_start_to_tx(self) -> int:
        return self._slot_duration * self._own_tx_slot + self._tx_start_end_buffer

    def set_has_gateway_link(self) -> None:
        if not self.link_established:
            self._set_own_hop_count(0)
            self._set_own_tx_slot(self._next_available_slot())  # get random slot
            self.discovery_state = DiscoverStates.DISCOVERED

    def enqueue_payload(self, payload: PayloadData | MegaSync) -> None:

        type = LoRaD2DFrameType.DATA_TO_GW
        destination_node_ids = set()
        if isinstance(payload, PayloadData):
            # get the two nodeids with lowest lower hopcount than own hop count
            sorted_neighbors = sorted(self._known_neighbors, key=lambda x: x.hopcount_to_gateway)
            for n in sorted_neighbors:
                if n.hopcount_to_gateway > self.hopcount_to_gateway or len(destination_node_ids) >= 2:
                    break
                destination_node_ids.add(n.neighbor_id)
        elif isinstance(payload, MegaSync):
            # get all nodeids with higher hopcount than own hop count
            type = LoRaD2DFrameType.DATA_FROM_GW
            for n in self._known_neighbors:
                if n.hopcount_to_gateway < self.hopcount_to_gateway:
                    continue

                destination_node_ids.add(n.neighbor_id)
        else:
            self._log.add(Severity.CRITICAL, Area.PROTOCOL, 0, "Node got unknown payload for routing....")
            return

        if len(destination_node_ids) == 0:
            self._log.add(Severity.WARNING, Area.PROTOCOL, 0, "Node have no destinations for payload....")

        msg = LoRaD2DFrame(
            source_node_id=self._node_id,
            destination_node_id=destination_node_ids,
            type=type,
            payload=payload,
        )

        msg.crc_calc()

        self._tx_buffer.append(msg)

    def dequeue_payload(self) -> list[PayloadData | MegaSync]:

        queue = []
        while self._rx_buffer:
            msg = self._rx_buffer.pop(0).payload
            if isinstance(msg, PayloadData) or isinstance(msg, MegaSync):
                queue.append(msg)  # Hop cnt messages are dropped.

        return queue

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, slot_period_counter: int) -> bool:

        current_transceiver_states = cast(dict[MediumTypes, TransceiverState], self._local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data)
        self.estimated_period_correction = 0

        is_start_and_has_valid_TX_slot = self.link_established and self._current_slot == -1 and self._own_tx_slot < self._slot_count
        # Add REDISCOVER for DEAD Nodes -> use last_seen to determine (only one for now)
        if is_start_and_has_valid_TX_slot:
            dead_node = next((n for n in self._known_neighbors if n.hopcount_to_gateway > self.hopcount_to_gateway and n.last_seen < current_local_clock_info.current_local_time - self.NEIGHBOR_DEAD_THREASHHOLD_MS), None)
            if dead_node:
                hop_cnt = PayloadHopCntFull(dead_node.hopcount_to_gateway, slot_period_counter=slot_period_counter, use_slot=dead_node.in_slot, time_offset_from_period_start=self._period_start_to_tx)
                msg = LoRaD2DFrame(source_node_id=self._node_id, destination_node_id={dead_node.neighbor_id}, type=LoRaD2DFrameType.REDISCOVER, payload=hop_cnt)
                msg.crc_calc()
                self._tx_buffer.append(msg)

        # add idle packet -> used for discovery
        # only add one for each period,and only if we know about two neighbors -> prevent situations where wrong hopcounts are calculated due to lack of info
        if not self._tx_buffer and is_start_and_has_valid_TX_slot:
            hop_cnt = PayloadHopCntFull(self.hopcount_to_gateway, slot_period_counter=slot_period_counter, time_offset_from_period_start=self._period_start_to_tx, use_slot=self._own_tx_slot)
            msg = LoRaD2DFrame(source_node_id=self._node_id, destination_node_id={0xFFFFFFFF}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_cnt)
            msg.crc_calc()
            self._tx_buffer.append(msg)
            self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} added idle packet with hop count {self.hopcount_to_gateway}")

        period_finished = self._advance_slot(current_local_clock_info)
        self._run_slot(current_global_tick, current_local_clock_info, current_transceiver_states)

        # process receptions and update neighbors, conflicting hop count info is resolved by taking the lowest hop count + 1 as our hop count
        self._process_receptions(current_global_tick, current_local_clock_info, slot_period_counter)

        # handle MINI SYNC here
        if period_finished:
            self._minisync()

        if not self.link_established:
            if self._run_discovery(current_global_tick, period_finished, current_local_clock_info, current_transceiver_states):
                period_finished = True  # signal wait for next period

        return period_finished

    def _run_discovery(self, current_global_tick: int, period_finished: bool, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict[MediumTypes, TransceiverState]) -> bool:
        if self.link_established:
            return False

        if self.discovery_state == DiscoverStates.NOT_DISCOVERED:
            self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.DISCOVERY_TIMEOUT_MS)
            self.discovery_state = DiscoverStates.LISTENING
            self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_clock if (current_global_clock := current_global_tick) else current_global_tick, f"Node {self._node_id} started D2D discovery")

        if self.discovery_state == DiscoverStates.LISTENING:
            hopcounts = {neighbor.hopcount_to_gateway for neighbor in self._known_neighbors}
            if len(hopcounts) >= 2:
                for hopcount in hopcounts:
                    if (hopcount + 1) in hopcounts:
                        self._set_own_hop_count(hopcount + 2)
                        self.discovery_state = DiscoverStates.REQ_ACK
                        self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} set hopcount to gateway {self.hopcount_to_gateway} from neighbors")
                        break
            elif len(self._known_neighbors) == 1:
                # Single neighbor case: discover from any neighbor, not just hopcount=0
                neighbor_hopcount = self._known_neighbors[0].hopcount_to_gateway
                if neighbor_hopcount < self.MAX_HOPCOUNT:
                    self._set_own_hop_count(neighbor_hopcount + 1)
                    self.discovery_state = DiscoverStates.REQ_ACK
                    self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} set hopcount to gateway {self.hopcount_to_gateway} from single neighbor with hopcount {neighbor_hopcount}")

            timer_1 = current_local_clock_info.timer_1_remaining
            if timer_1 is not None and timer_1 <= 0:
                if len(self._known_neighbors) == 1 and self._known_neighbors[0].hopcount_to_gateway == 0:
                    self._set_own_hop_count(1)
                    self.discovery_state = DiscoverStates.REQ_ACK
                    self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} set hopcount to gateway 1 based on single neighbor")
                elif len(self._known_neighbors) > 0:
                    # have at least one neighbor but not the right pattern - use min neighbor hopcount + 1
                    min_neighbor_hop = min(n.hopcount_to_gateway for n in self._known_neighbors)
                    if min_neighbor_hop < self.MAX_HOPCOUNT:
                        self._set_own_hop_count(min_neighbor_hop + 1)
                        self.discovery_state = DiscoverStates.REQ_ACK
                        self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} set hopcount to gateway {self.hopcount_to_gateway} from min neighbor")
                    else:
                        self.discovery_state = DiscoverStates.NOT_DISCOVERED
                        self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
                        self.estimated_period_start = 0
                        self.slot_period_counter = 0
                        return True
                else:
                    self.discovery_state = DiscoverStates.NOT_DISCOVERED
                    self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
                    self.estimated_period_start = 0
                    self.slot_period_counter = 0
                    return True

        if self.discovery_state == DiscoverStates.WAIT_REQ_ACK_SENT and period_finished:
            self.discovery_state = DiscoverStates.WAITING_FOR_ACK
            self.estimated_period_start = self._slot_period_start
            return True  # signal wait for next period

        if self.discovery_state == DiscoverStates.WAITING_FOR_ACK and period_finished:
            # we wait for ACK, if we receive it we will set our state to DISCOVERED in the reception processing,
            # if we do not receive it before the end of the period we will need to retry in the next period
            self.discovery_state = DiscoverStates.REQ_ACK
            self.estimated_period_start = self._slot_period_start

        if self.discovery_state == DiscoverStates.REQ_ACK:
            if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
                self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

            # we have selected a hop count, we need to request ACK from neighbors with that hop
            # dest node should be the lowest hop count node known (closest to gateway, has authority)
            dest_node_id = min(self._known_neighbors, key=lambda x: x.hopcount_to_gateway).neighbor_id
            frame = LoRaD2DFrame(source_node_id=self._node_id, destination_node_id={dest_node_id}, type=LoRaD2DFrameType.REQ_HOP_ACK, payload=PayloadHopCntSimple(cnt=self.hopcount_to_gateway))
            frame.crc_calc()
            self._tx_buffer.append(frame)
            # We need to retry ACK in new random mini-slot to avoid collisions with other nodes retrying at the same time
            self._offset_for_req_ack = self._rnd.choice(range(self._mini_slot_count)) * (self._slot_duration // self._mini_slot_count)

            # self.discovery_state = DiscoverStates.WAITING_FOR_ACK
            self.discovery_state = DiscoverStates.WAIT_REQ_ACK_SENT
            self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} sent REQ_HOP_ACK to node {dest_node_id} with hop count {self.hopcount_to_gateway}, with offset {self._offset_for_req_ack}ms")

            return True  # signal wait for next period

        return False

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> bool:
        if not (self.link_established or self.discovery_state in [DiscoverStates.WAIT_REQ_ACK_SENT, DiscoverStates.WAITING_FOR_ACK]):
            return False

        timer_1 = current_local_clock_info.timer_1_remaining
        if not (timer_1 is None or timer_1 == 0):
            return False

        if self._current_slot == -1:
            self._slot_period_start = current_local_clock_info.current_local_time

        self._current_slot += 1
        if self._current_slot < self._slot_count:
            self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self._slot_duration)
            if self._current_slot == self._own_tx_slot:
                offset = self._offset_for_req_ack if self.discovery_state == DiscoverStates.WAIT_REQ_ACK_SENT else self._tx_start_end_buffer
                self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_2, data=offset)
                self._tx_offset_done = False
            return False

        self._current_slot = -1
        self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
        self._tx_offset_done = False
        return True

    def _run_slot(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict[MediumTypes, TransceiverState]) -> None:
        if self._current_slot < 0:
            return

        current_local_time = current_local_clock_info.current_local_time
        slot_end_in = current_local_clock_info.timer_1_remaining
        timer_2 = current_local_clock_info.timer_2_remaining
        is_tx_slot = self._current_slot == self._own_tx_slot

        if not is_tx_slot:
            if current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.RECEIVING:
                self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            return

        if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
            self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

        if self._tx_buffer and current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.TRANSMITTING and ((timer_2 is not None and timer_2 <= 0) or self._tx_offset_done):  # ((timer_2 is not None and timer_2 <= 0) or self._tx_offset_done)
            self._tx_offset_done = True
            self._tx_buffer.sort(key=lambda f: f.type)  # Ensure highest priority packets are sent first, currently priority is determined by frame type order in LoRaD2DFrameType enum
            # determine if time allow for packet tx
            tx_duration = self._duration_calculator.get_duration(self._tx_buffer[0].length)
            if slot_end_in is None or tx_duration > slot_end_in - self._tx_start_end_buffer:
                return

            packet = self._tx_buffer.pop(0)

            if isinstance(packet.payload, MegaSync):
                self._handle_megasync_packet(packet.payload, current_local_time, tx_duration)

            self._local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_D2D, data=packet)

    def _process_receptions(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, current_slot_period_counter: int) -> None:
        current_receptions = self._local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_D2D)
        if not current_receptions:
            return

        # we process each packet as it is received so only one packet is there at a time
        frame = cast(LoRaD2DFrame, current_receptions[0].data)
        match frame.type:
            case LoRaD2DFrameType.CURRENT_HOP_COUNT:
                self._process_current_hopcount(frame, current_local_clock_info.current_local_time, current_slot_period_counter)

            case LoRaD2DFrameType.DATA_TO_GW:
                if self._node_id in frame.destination_node_id:
                    self._rx_buffer.append(frame)

            case LoRaD2DFrameType.DATA_FROM_GW:
                if self._node_id in frame.destination_node_id:
                    if isinstance(frame.payload, MegaSync):
                        frame.payload.local_rx_time = current_local_clock_info.current_local_time
                    self._rx_buffer.append(frame)

            case LoRaD2DFrameType.REQ_HOP_ACK:
                if self._node_id in frame.destination_node_id:
                    self._process_req_hop_ack(frame, current_local_clock_info.current_local_time, current_slot_period_counter)

            case LoRaD2DFrameType.CHANGE_HOP_COUNT:
                self._process_change_hop_count(frame, current_global_tick, current_slot_period_counter)

            case LoRaD2DFrameType.REDISCOVER:
                # we have been dead and now been directly synced
                if self._node_id in frame.destination_node_id:
                    self.discovery_state = DiscoverStates.DISCOVERED

                    payload = cast(PayloadHopCntFull, frame.payload)
                    self.estimated_period_start = current_local_clock_info.current_local_time - (payload.time_offset_from_period_start + self._duration_calculator.get_duration(frame.length) + 2)
                    self.slot_period_counter = payload.slot_period_counter
                    self._set_own_hop_count(payload.cnt)
                    self._set_own_tx_slot(payload.use_slot)

                    self._log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} discovery complete with hop count {self.hopcount_to_gateway}, use TX slot: {self._own_tx_slot}")

        # update last seen for neighbor
        existing = next((n for n in self._known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing:
            if existing.last_seen < self._slot_period_start:
                existing.first_tx_start_time_in_period = current_local_clock_info.current_local_time - self._duration_calculator.get_duration(frame.length) - 2  # account for local_event_queue in TX and RX (2 ticks)
                if self._current_slot > -1:
                    existing.in_slot = self._current_slot

            existing.last_seen = current_local_clock_info.current_local_time
            existing.last_rssi = frame.rssi

    def _process_current_hopcount(self, frame: LoRaD2DFrame, current_local_time: int, current_slot_period_counter: int) -> None:
        frame_hop_cnt = cast(PayloadHopCntFull, frame.payload)

        # update observed slot registry (all nodes in range, not just known neighbors)
        self._observed_slots[frame.source_node_id] = frame_hop_cnt.use_slot

        if self.discovery_state in (DiscoverStates.NOT_DISCOVERED, DiscoverStates.LISTENING):
            self.estimated_period_start = current_local_time - (frame_hop_cnt.time_offset_from_period_start + self._duration_calculator.get_duration(frame.length) + 2)
            self.slot_period_counter = frame_hop_cnt.slot_period_counter

        existing = next((n for n in self._known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing is None:
            neighbor_info = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=frame_hop_cnt.cnt, last_seen=current_local_time, last_rssi=frame.rssi, in_slot=frame_hop_cnt.use_slot, first_tx_start_time_in_period=0)
            self._known_neighbors.append(neighbor_info)
        else:
            existing.hopcount_to_gateway = frame_hop_cnt.cnt

        self._resolve_upstream_hopcount_and_slot(current_slot_period_counter)

    def _process_change_hop_count(self, frame: LoRaD2DFrame, current_global_tick: int, current_slot_period_counter: int) -> None:

        # we have been instructed to change our hop count, update our hop count to the instructed hop count
        # implied ACk, we can assume discovery complete
        payload = cast(PayloadHopCntMid, frame.payload)
        if self._node_id in frame.destination_node_id:
            if self.discovery_state != DiscoverStates.DISCOVERED:
                self.estimated_period_start = self._slot_period_start
                self.slot_period_counter = payload.slot_period_counter

            self.discovery_state = DiscoverStates.DISCOVERED

            self._set_own_hop_count(payload.cnt)
            self._set_own_tx_slot(payload.use_slot)

            self._log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} discovery complete with hop count {self.hopcount_to_gateway}, use TX slot: {self._own_tx_slot}")
            self._observed_slots[self._node_id] = self._own_tx_slot  # keep registry self-consistent

        elif frame.destination_node_id and abs(payload.cnt - self.hopcount_to_gateway) <= 2:
            # is for a node in reach -> track slot without corrupting known_neighbors RSSI
            nid = next(iter(frame.destination_node_id))  # peek without popping
            self._observed_slots[nid] = payload.use_slot
            # update existing neighbor if already known
            existing = next((n for n in self._known_neighbors if n.neighbor_id == nid), None)
            if existing is not None:
                existing.hopcount_to_gateway = payload.cnt
                existing.in_slot = payload.use_slot
        else:
            # Remove destination nodes whose hopcount has increased by more than 2 from our own
            for node_id in frame.destination_node_id & self._observed_slots.keys():  # only observed nodes
                if abs(payload.cnt - self.hopcount_to_gateway) > 2:
                    self._observed_slots.pop(node_id)
                    self._log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self._node_id} removed node {node_id} from observed slots")

        self._resolve_upstream_hopcount_and_slot(current_slot_period_counter)

    def _process_req_hop_ack(self, frame: LoRaD2DFrame, current_local_time: int, current_slot_period_counter: int) -> None:

        # TODO: handle edge case where we have more neighbors than slots... (we currently log the event)
        # TODO: handle where slot conflicts amung lower hopcount nodes e.g. V sahpe where both nodes have GW connection
        # Maybe REQ conflicting nodes to send used slots and see if resolution is possible, then send CHANGE_HOP_COUNT

        frame_hop_cnt = cast(PayloadHopCntSimple, frame.payload)

        validate_hopcount = frame_hop_cnt.cnt

        # find requesting node in known neighbors and update hop count if needed
        neighbor = next((n for n in self._known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if neighbor is None:
            neighbor = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=validate_hopcount, last_seen=current_local_time, last_rssi=frame.rssi, in_slot=-1, first_tx_start_time_in_period=0)
            self._known_neighbors.append(neighbor)
        elif neighbor.hopcount_to_gateway != validate_hopcount:
            neighbor.hopcount_to_gateway = validate_hopcount
            neighbor.last_rssi = frame.rssi

        self._resolve_upstream_hopcount_and_slot(current_slot_period_counter)

    def _next_available_slot(self) -> int:
        # we have observed all slots used, we try to remove all where we havent heared directly from
        if len(self._observed_slots) == self._slot_count - 1:
            self._log.add(Severity.WARNING, Area.PROTOCOL, 0, f"Node {self._node_id} have used all slots, trying to remove unused...")
            known = {n.neighbor_id for n in self._known_neighbors}
            for nid in list(self._observed_slots.keys()):
                if nid not in known:
                    del self._observed_slots[nid]

        # find new slot deterministic
        # used = set(self._observed_slots.values()) | {self._own_tx_slot}
        # start = (self._own_tx_slot % (self._slot_count - 1)) + 1
        # for i in range(1, self._slot_count):
        #     slot = (start - 1 + i) % (self._slot_count - 1) + 1
        #     if slot not in used:
        #         return slot
        # self._log.add(Severity.CRITICAL, Area.PROTOCOL, 0, f"Node {self._node_id} slot exhaustion to node {neighbor.neighbor_id}")
        # return 0

        # find new random slot
        used = set(self._observed_slots.values()) | {self._own_tx_slot}
        valid = set(range(1, self._slot_count))
        available = valid.difference(used)
        if not available:
            self._log.add(Severity.CRITICAL, Area.PROTOCOL, 0, f"Node {self._node_id} slot exhaustion")
            return self._slot_count  # invalid slot -> no TX
        return self._rnd.choice(list(available))

    def _get_slot_for_node(self, neighbor: D2DNeighborInfo) -> int:
        # if current used slot is valid, return the current
        # otherwise find new valid slot

        # have slot -> check if still valid
        if neighbor is not None and neighbor.in_slot > -1 and neighbor.in_slot < self._slot_count:
            conflicting = next((nid for (nid, sidx) in self._observed_slots.items() if sidx == neighbor.in_slot and nid != neighbor.neighbor_id), None)
            if not conflicting:
                return neighbor.in_slot

        self._log.add(Severity.DEBUG, Area.PROTOCOL, 0, f"Node {self._node_id}, find slot for nid: {neighbor.neighbor_id}, used slots: {self._observed_slots}")

        return self._next_available_slot()

    def _resolve_upstream_hopcount_and_slot(self, current_slot_period_counter: int) -> None:

        # order list by best RSSI
        self._known_neighbors.sort(key=lambda x: -x.last_rssi)

        # only iterate on downstream neighbors (higher hopcount than self)
        of_interest = (neighbor for neighbor in self._known_neighbors if neighbor.hopcount_to_gateway > self.hopcount_to_gateway)
        current_hop = self.hopcount_to_gateway
        prev_rssi = 0
        rssi_threshold = 6
        for neighbor in of_interest:
            if abs(prev_rssi - neighbor.last_rssi) > rssi_threshold:
                prev_rssi = neighbor.last_rssi
                current_hop += 1  # increment by one for each "layer"

            use_slot = self._get_slot_for_node(neighbor)
            if neighbor.hopcount_to_gateway == current_hop and neighbor.in_slot == use_slot:
                continue  # no change needed

            neighbor.hopcount_to_gateway = current_hop
            neighbor.in_slot = use_slot
            self._observed_slots[neighbor.neighbor_id] = neighbor.in_slot
            change_frame = LoRaD2DFrame(source_node_id=self._node_id, destination_node_id={neighbor.neighbor_id}, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=PayloadHopCntMid(cnt=current_hop, use_slot=neighbor.in_slot, slot_period_counter=current_slot_period_counter))
            change_frame.crc_calc()

            existing_frame_index = next((i for i, f in enumerate(self._tx_buffer) if neighbor.neighbor_id in f.destination_node_id and f.type == LoRaD2DFrameType.CHANGE_HOP_COUNT), None)
            if existing_frame_index is not None:
                self._tx_buffer[existing_frame_index] = change_frame
            else:
                self._tx_buffer.append(change_frame)

        self._known_neighbors.sort(key=lambda x: (x.hopcount_to_gateway, -x.last_rssi))

    def _minisync(self) -> None:
        if not self.link_established or not self._known_neighbors:
            return

        if self.estimated_period_correction > 0:
            return  # MegaSync has happened in current period

        slot_offsets = []
        for n in self._known_neighbors:
            # ignore if not seen in this slot period e.g a dead node
            if n.last_seen < self._slot_period_start or n.first_tx_start_time_in_period < self._slot_period_start:
                continue

            # calculate diff between local start time of slot and the observed tx time
            slot_start = self._slot_period_start + (n.in_slot * self._slot_duration) + self._tx_start_end_buffer
            observed_start = n.first_tx_start_time_in_period
            # relative correction, negative means we are ahead while positive means behind
            # fx. observed: 102, start: 100 -> 100 - 102 = -2
            correction = observed_start - slot_start
            slot_offsets.append(correction)

        if not slot_offsets:
            return

        # simple average -> simplest
        # current_offset = sum(slot_offsets) / len(slot_offsets)

        # median -> f occasional large outliers (missed packets, delayed RX timestamps, collisions), then median is often more stable
        current_offset = statistics.median(slot_offsets)

        self.estimated_period_correction = int(current_offset)

        # lowpass with prev correction to avoid oscillation and over-correction
        # alpha = 0.2
        # self.estimated_period_correction = int((alpha * current_offset + (1 - alpha) * self.estimated_relative_period_offset))

    def _handle_megasync_packet(self, packet: MegaSync, current_local_time: int, tx_duration: int) -> None:

        # add internal process time
        packet.total_handle_time += current_local_time - packet.local_rx_time

        # calculate local time diff from synced time
        # relative correction, negative means we are ahead while positive means behind
        # fx. own_time: 102, sync_time: 100 -> 100 - 102 = -2
        self.estimated_period_correction = current_local_time - packet.time + packet.total_handle_time

        # add tx time for nex node
        packet.total_handle_time += tx_duration + 1

    def _set_own_hop_count(self, hop_count: int) -> None:
        if self.hopcount_to_gateway == hop_count:
            return

        self.hopcount_to_gateway = hop_count
        # update scheduled CURRENT_HOP_COUNT frames in tx_buffer
        if not self._tx_buffer:
            return

        if self._tx_buffer[0].type == LoRaD2DFrameType.CURRENT_HOP_COUNT and isinstance(self._tx_buffer[0].payload, PayloadHopCntFull):
            self._tx_buffer[0].payload.cnt = hop_count

    def _set_own_tx_slot(self, tx_slot: int) -> None:
        if self._own_tx_slot == tx_slot:
            return

        self._own_tx_slot = tx_slot
        # update scheduled CURRENT_HOP_COUNT frames in tx_buffer
        if not self._tx_buffer:
            return

        if self._tx_buffer[0].type == LoRaD2DFrameType.CURRENT_HOP_COUNT and isinstance(self._tx_buffer[0].payload, PayloadHopCntFull):
            self._tx_buffer[0].payload.use_slot = tx_slot
