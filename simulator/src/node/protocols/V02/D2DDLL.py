from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import List, cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaD2DFrame, LoRaD2DFrameType, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue


@dataclass
class D2DNeighborInfo:
    neighbor_id: int
    hopcount_to_gateway: int
    last_seen: int
    last_rssi: int


class DiscoverStates(Enum):
    NOT_DISCOVERED = 0
    LISTENING = 1
    REQ_ACK = 2
    WAITING_FOR_ACK = 3
    DISCOVERED = 4


class D2DDLL:
    DISCOVERY_TIMEOUT_MS = 60_000 + 10 * 1000
    MAX_HOPCOUNT = 65535

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, slot_duration: int = 100, slot_count: int = 5):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.slot_duration = slot_duration
        self.slot_count = slot_count
        self.mini_slot_count = 3
        self.current_slot = -1
        self.current_tx_slot = -1
        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.hopcount_to_gateway = self.MAX_HOPCOUNT
        self.known_neighbors: List[D2DNeighborInfo] = []
        self.discovery_state = DiscoverStates.NOT_DISCOVERED
        self.tx_buffer: List[LoRaD2DFrame] = []
        self.rx_buffer: List[LoRaD2DFrame] = []
        self.current_slot = -1
        self.current_tx_slot = -1
        self.rnd = Random(self.node_id)

    @property
    def link_established(self) -> bool:
        return self.hopcount_to_gateway < self.MAX_HOPCOUNT and self.discovery_state == DiscoverStates.DISCOVERED

    def set_has_gateway_link(self) -> None:
        if not self.link_established:
            self.hopcount_to_gateway = 0
            self.discovery_state = DiscoverStates.DISCOVERED

    def enqueue_payload(self, payload: bytes) -> None:
        self.tx_buffer.append(
            LoRaD2DFrame(
                source_node_id=self.node_id,
                destination_node_id=0xFFFFFFFF,  # TODO: set destination to next hop instead of broadcast
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
        )

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> bool:

        current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data

        if not self.link_established:
            self._run_discovery(current_global_tick, current_local_clock_info)
            # TODO: we should estimate next period start, currently relying on ideal clock...

        # add idle packet -> used for discovery
        if not self.tx_buffer and self.link_established:
            self.tx_buffer.append(LoRaD2DFrame(source_node_id=self.node_id, destination_node_id=0xFFFFFFFF, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=self.hopcount_to_gateway.to_bytes(2, "big")))

        period_finished = self._advance_slot(current_local_clock_info)
        self._run_slot(current_global_tick, current_local_clock_info, current_transceiver_states)

        # process receptions and update neighbors, conflicting hop count info is resolved by taking the lowest hop count + 1 as our hop count
        self._process_receptions(current_global_tick, current_local_clock_info)

        # True if not period_finished and self.discovery_state == DiscoverStates.WAITING_FOR_ACK and period not in progress
        # True if period_finished and self.link_established
        discover_wait_next_period = not period_finished and self.discovery_state == DiscoverStates.WAITING_FOR_ACK and self.current_slot == -1
        default = period_finished and self.link_established
        return default or discover_wait_next_period

    def _run_discovery(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> None:
        if self.link_established:
            return

        if self.discovery_state == DiscoverStates.NOT_DISCOVERED:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.DISCOVERY_TIMEOUT_MS)
            self.discovery_state = DiscoverStates.LISTENING
            self.log.add(Severity.INFO, Area.PROTOCOL, current_global_clock if (current_global_clock := current_global_tick) else current_global_tick, f"Node {self.node_id} started D2D discovery")

        if self.discovery_state == DiscoverStates.LISTENING:
            hopcounts = {neighbor.hopcount_to_gateway for neighbor in self.known_neighbors}
            if len(hopcounts) >= 2:
                for hopcount in hopcounts:
                    if (hopcount + 1) in hopcounts:
                        self.hopcount_to_gateway = hopcount + 2
                        self.discovery_state = DiscoverStates.REQ_ACK
                        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway {self.hopcount_to_gateway} from neighbors")
                        break

            timer_1 = current_local_clock_info.timer_1_remaining
            if timer_1 is not None and timer_1 <= 0 and not self.link_established:
                if len(self.known_neighbors) == 1 and self.known_neighbors[0].hopcount_to_gateway == 0:
                    self.hopcount_to_gateway = 1
                    self.discovery_state = DiscoverStates.REQ_ACK
                    self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway 1 based on single neighbor")
                else:
                    self.discovery_state = DiscoverStates.NOT_DISCOVERED

        if self.discovery_state == DiscoverStates.REQ_ACK:
            # we have selected a hop count, we need to request ACK from neighbors with that hop
            # dest node should be the lowest hop count node known
            dest_node_id = min(self.known_neighbors, key=lambda x: x.hopcount_to_gateway).neighbor_id
            frame = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id=dest_node_id, type=LoRaD2DFrameType.REQ_HOP_ACK, payload=self.hopcount_to_gateway.to_bytes(2, "big"))
            self.tx_buffer.append(frame)
            self.discovery_state = DiscoverStates.WAITING_FOR_ACK
            # We need to retry ACK in new random mini-slot to avoid collisions with other nodes retrying at the same time
            self.mini_slot_for_ack = self.rnd.choice(range(self.mini_slot_count))
            # TODO: somehow signal we need to tx at a random mini slot in the current slot period to avoid collisions with other nodes sending ACKs at the same time
            # determine when the next period starts

        timer_1 = current_local_clock_info.timer_1_remaining
        if self.discovery_state == DiscoverStates.WAITING_FOR_ACK and self.current_slot == self.slot_count - 1 and (timer_1 is None or timer_1 == 0):
            # we wait for ACK, if we receive it we will set our state to DISCOVERED in the reception processing,
            # if we do not receive it before the end of the period we will need to retry in the next period
            self.discovery_state = DiscoverStates.REQ_ACK

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> bool:
        if not (self.link_established or self.discovery_state in [DiscoverStates.REQ_ACK, DiscoverStates.WAITING_FOR_ACK]):
            return False

        timer_1 = current_local_clock_info.timer_1_remaining
        if not (timer_1 is None or timer_1 == 0):
            return False

        self.current_slot += 1
        if self.current_slot < self.slot_count:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.slot_duration)
            if self.current_slot == self.current_tx_slot:
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_2, data=10)
            return False

        self.current_slot = -1
        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
        return True

    def _run_slot(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict) -> None:
        if self.current_slot < 0:
            return

        timer_2 = current_local_clock_info.timer_2_remaining
        is_tx_slot = self.current_slot == self.current_tx_slot

        if not is_tx_slot:
            if current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.RECEIVING:
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            return

        if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

        if self.tx_buffer and current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.TRANSMITTING and timer_2 is not None and timer_2 <= 0:
            # TODO: determine if tiem allow for packet tx other wise wait until next slot
            packet = self.tx_buffer.pop(0)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_D2D, data=packet)

    def _process_receptions(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> None:
        current_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_D2D)
        if not current_receptions:
            return

        # we process each packet as it is received so only one packet is there ata a time
        frame = cast(LoRaD2DFrame, current_receptions[0].data)
        match frame.type:
            case LoRaD2DFrameType.CURRENT_HOP_COUNT:
                self._process_current_hopcount(frame, current_local_clock_info.current_local_time)

            case LoRaD2DFrameType.DATA_TO_GW:
                if frame.destination_node_id == self.node_id:
                    self.rx_buffer.append(frame)

            case LoRaD2DFrameType.DATA_FROM_GW:
                if frame.destination_node_id == self.node_id:
                    self.rx_buffer.append(frame)

            case LoRaD2DFrameType.REQ_HOP_ACK:
                if frame.destination_node_id == self.node_id:
                    self._process_req_hop_ack(frame)

            case LoRaD2DFrameType.HOP_ACK:
                # we have been ACKed,  we can assume discovery complete
                if frame.destination_node_id == self.node_id:
                    self.discovery_state = DiscoverStates.DISCOVERED

            case LoRaD2DFrameType.CHANGE_HOP_COUNT:
                # we have been instructed to change our hop count, update our hop count to the instructed hop count
                # implied ACk, we can assume discovery complete
                if frame.destination_node_id == self.node_id:
                    self.discovery_state = DiscoverStates.DISCOVERED
                    self.hopcount_to_gateway = int.from_bytes(frame.payload, "big")

        # update last seen for neighbor
        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing:
            existing.last_seen = current_local_clock_info.current_local_time
            existing.last_rssi = frame.rssi

    def _process_current_hopcount(self, frame: LoRaD2DFrame, current_local_time: int) -> None:
        hopcount = int.from_bytes(frame.payload, "big")

        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing is None:
            neighbor_info = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=hopcount, last_seen=current_local_time)
            self.known_neighbors.append(neighbor_info)

    def _process_req_hop_ack(self, frame: LoRaD2DFrame, current_local_time: int) -> None:

        # TODO: handle edge case where we have more neighbors than slots...

        validate_hopcount = int.from_bytes(frame.payload, "big")

        # find requesting node in known neighbors and update hop count if needed
        neighbor = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if neighbor is None:
            neighbor = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=validate_hopcount, last_seen=current_local_time, last_rssi=frame.rssi)
            self.known_neighbors.append(neighbor)
        elif neighbor.hopcount_to_gateway != validate_hopcount:
            neighbor.hopcount_to_gateway = validate_hopcount
            neighbor.last_seen = current_local_time
            neighbor.last_rssi = frame.rssi

        # order list by lowest hopcount then by best RSSI
        self.known_neighbors.sort(key=lambda x: (x.hopcount_to_gateway, -x.last_rssi))

        # only iterate on neighbors with higher hopcount than own
        of_interest = (neighbor for neighbor in self.known_neighbors if neighbor.hopcount_to_gateway > self.hopcount_to_gateway)
        for i_relative, neighbor in enumerate(of_interest):
            new_hop_count = self.hopcount_to_gateway + 1 + i_relative
            if neighbor.hopcount_to_gateway == new_hop_count:
                if neighbor.neighbor_id == frame.source_node_id:
                    ack_frame = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id=neighbor.neighbor_id, type=LoRaD2DFrameType.HOP_ACK, payload=new_hop_count.to_bytes(2, "big"))
                    self.tx_buffer.append(ack_frame)

                continue

            neighbor.hopcount_to_gateway = new_hop_count
            change_frame = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id=neighbor.neighbor_id, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=new_hop_count.to_bytes(2, "big"))
            existing_frame_index = next((i for i, f in enumerate(self.tx_buffer) if f.destination_node_id == neighbor.neighbor_id and f.type in [LoRaD2DFrameType.CHANGE_HOP_COUNT, LoRaD2DFrameType.HOP_ACK]), None)
            if existing_frame_index is not None:
                self.tx_buffer[existing_frame_index] = change_frame
            else:
                self.tx_buffer.append(change_frame)
