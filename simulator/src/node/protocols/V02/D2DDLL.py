from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import List, cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaD2DFrame, LoRaD2DFrameType, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.transceiver.lora_tx_duration_calculator import LoRaTxDurationCalculator
from payload_types import MegaSync, PayloadData, PayloadHopCnt


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
    MAX_HOPCOUNT = 65535

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, slot_duration: int = 110, slot_count: int = 5):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.slot_duration = slot_duration
        self.slot_count = slot_count
        self.mini_slot_count = 3
        self.duration_calculator = LoRaTxDurationCalculator(second_to_global_tick=0.001) # in ms
        self.reset(0)

    def reset(self, current_global_tick: int) -> None:
        self.hopcount_to_gateway = self.MAX_HOPCOUNT
        self.known_neighbors: List[D2DNeighborInfo] = []
        self.discovery_state = DiscoverStates.NOT_DISCOVERED
        self.tx_buffer: List[LoRaD2DFrame] = []
        self.rx_buffer: List[LoRaD2DFrame] = []
        self.current_slot = -1
        self.own_tx_slot = -1
        self.offset_for_req_ack = 0
        self.tx_start_edn_buffer = 10
        self.tx_offset_done = False
        self.rnd = Random(self.node_id)
        self.slot_period_start = 0
        
    @property
    def link_established(self) -> bool:
        return self.hopcount_to_gateway < self.MAX_HOPCOUNT and self.discovery_state == DiscoverStates.DISCOVERED

    def set_has_gateway_link(self) -> None:
        if not self.link_established:
            self._update_local_hopcount(0)
            self.discovery_state = DiscoverStates.DISCOVERED

    def enqueue_payload(self, payload: PayloadHopCnt | PayloadData | MegaSync) -> None:

        destination_node_ids = set()
        if isinstance(payload, PayloadData):
            # get the two nodeids with lowest lower hopcount than own hop count
            sorted_neighbors = sorted(self.known_neighbors, key=lambda x: x.hopcount_to_gateway)
            for n in sorted_neighbors:
                if n.hopcount_to_gateway > self.hopcount_to_gateway or len(destination_node_ids) >= 2:
                    break
                destination_node_ids.add(n.neighbor_id)
        elif isinstance(payload, MegaSync):
            # get all nodeids with higher hopcount than own hop count
            for n in self.known_neighbors:
                if n.hopcount_to_gateway < self.hopcount_to_gateway:
                    continue

                destination_node_ids.add(n.neighbor_id)
        else:
            self.log.add(Severity.CRITICAL, Area.PROTOCOL, 0, "Node got unknown payload for routing....")
            return

        if len(destination_node_ids) == 0:
            self.log.add(Severity.CRITICAL, Area.PROTOCOL, 0, "Node have no destinations for payload.... dropped")

        msg = LoRaD2DFrame(
            source_node_id=self.node_id,
            destination_node_id=destination_node_ids,
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload,
        )

        msg.crc_calc()

        self.tx_buffer.append(msg)

    def dequeue_payload(self) -> list[PayloadData | MegaSync]:

        queue = []
        while self.rx_buffer:
            msg = self.rx_buffer.pop(0).payload
            if isinstance(msg, PayloadData) or isinstance(msg, MegaSync):
                queue.append(msg)  # Hop cnt messages are dropped.

        return queue

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> bool:

        current_transceiver_states = cast(dict[MediumTypes, TransceiverState], self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data)

        # add idle packet -> broadcast hopcount during listening/forwarding (so discovering nodes learn about us)
        if not self.tx_buffer and self.current_slot == -1 and (self.link_established or self.discovery_state == DiscoverStates.LISTENING):
            hop_cnt = PayloadHopCnt(self.hopcount_to_gateway)
            msg = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id={0xFFFFFFFF}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_cnt)
            msg.crc_calc()
            self.tx_buffer.append(msg)
            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} added idle packet with hop count {self.hopcount_to_gateway}")

        period_finished = self._advance_slot(current_local_clock_info)
        self._run_slot(current_global_tick, current_local_clock_info, current_transceiver_states)

        # process receptions and update neighbors, conflicting hop count info is resolved by taking the lowest hop count + 1 as our hop count
        self._process_receptions(current_global_tick, current_local_clock_info)

        if not self.link_established:
            if self._run_discovery(current_global_tick, period_finished, current_local_clock_info, current_transceiver_states):
                period_finished = True  # signal wait for next period
            # TODO: we should estimate next period start, currently relying on ideal clock...

        return period_finished

    def _run_discovery(self, current_global_tick: int, period_finished: bool, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict[MediumTypes, TransceiverState]) -> bool:
        if self.link_established:
            return False

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
                        self._update_local_hopcount(hopcount + 2)
                        self.discovery_state = DiscoverStates.REQ_ACK
                        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway {self.hopcount_to_gateway} from neighbors")
                        break
            elif len(self.known_neighbors) == 1:
                # Single neighbor case: discover from any neighbor, not just hopcount=0
                neighbor_hopcount = self.known_neighbors[0].hopcount_to_gateway
                if neighbor_hopcount < self.MAX_HOPCOUNT:
                    self._update_local_hopcount(neighbor_hopcount + 1)
                    self.discovery_state = DiscoverStates.REQ_ACK
                    self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway {self.hopcount_to_gateway} from single neighbor with hopcount {neighbor_hopcount}")

            timer_1 = current_local_clock_info.timer_1_remaining
            if timer_1 is not None and timer_1 <= 0:
                if self.discovery_state == DiscoverStates.LISTENING:
                    # Timer expired without discovery
                    self.discovery_state = DiscoverStates.NOT_DISCOVERED
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
                    return True

        if self.discovery_state == DiscoverStates.WAIT_REQ_ACK_SENT and period_finished:
            self.discovery_state = DiscoverStates.WAITING_FOR_ACK
            return True  # signal wait for next period

        if self.discovery_state == DiscoverStates.WAITING_FOR_ACK and period_finished:
            # we wait for ACK, if we receive it we will set our state to DISCOVERED in the reception processing,
            # if we do not receive it before the end of the period we will need to retry in the next period
            self.discovery_state = DiscoverStates.REQ_ACK

        if self.discovery_state == DiscoverStates.REQ_ACK:
            if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

            # we have selected a hop count, we need to request ACK from neighbors with that hop
            # dest node should be the lowest hop count node known
            dest_node_id = min(self.known_neighbors, key=lambda x: x.hopcount_to_gateway).neighbor_id
            frame = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id={dest_node_id}, type=LoRaD2DFrameType.REQ_HOP_ACK, payload=PayloadHopCnt(cnt=self.hopcount_to_gateway))
            frame.crc_calc()
            self.tx_buffer.append(frame)
            # We need to retry ACK in new random mini-slot to avoid collisions with other nodes retrying at the same time
            self.offset_for_req_ack = self.rnd.choice(range(self.mini_slot_count)) * (self.slot_duration // self.mini_slot_count)

            # self.discovery_state = DiscoverStates.WAITING_FOR_ACK
            self.discovery_state = DiscoverStates.WAIT_REQ_ACK_SENT
            self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} sent REQ_HOP_ACK to node {dest_node_id} with hop count {self.hopcount_to_gateway}, with offset {self.offset_for_req_ack}ms")
            return True  # signal wait for next period
            # TODO: determine when the next period starts based on known rx timeses

        return False

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> bool:
        if not (self.link_established or self.discovery_state in [DiscoverStates.LISTENING, DiscoverStates.WAIT_REQ_ACK_SENT, DiscoverStates.WAITING_FOR_ACK]):
            return False

        timer_1 = current_local_clock_info.timer_1_remaining
        if not (timer_1 is None or timer_1 == 0):
            return False

        if self.current_slot == -1:
            self.slot_period_start = current_local_clock_info.current_local_time

        self.current_slot += 1        
        if self.current_slot < self.slot_count:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.slot_duration)
            if self.current_slot == self.own_tx_slot:
                offset = self.offset_for_req_ack if self.discovery_state == DiscoverStates.WAIT_REQ_ACK_SENT else self.tx_start_edn_buffer
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_2, data=offset)
                self.tx_offset_done = False
            return False

        self.current_slot = -1
        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
        self.tx_offset_done = False
        return True

    def _run_slot(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, current_transceiver_states: dict[MediumTypes, TransceiverState]) -> None:
        if self.current_slot < 0:
            return

        slot_end_in = current_local_clock_info.timer_1_remaining
        timer_2 = current_local_clock_info.timer_2_remaining
        is_tx_slot = self.current_slot == self.own_tx_slot

        if not is_tx_slot:
            if current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.RECEIVING:
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            return

        if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

        if self.tx_buffer and current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.TRANSMITTING and ((timer_2 is not None and timer_2 <= 0) or self.tx_offset_done):  # ((timer_2 is not None and timer_2 <= 0) or self.tx_offset_done)
            self.tx_offset_done = True
            self.tx_buffer.sort(key=lambda f: f.type)  # Ensure highest priority packets are sent first, currently priority is determined by frame type order in LoRaD2DFrameType enum
            # determine if time allow for packet tx
            if self.duration_calculator.get_duration(self.tx_buffer[0].length) > slot_end_in - self.tx_start_edn_buffer:
                return 

            packet = self.tx_buffer.pop(0)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_D2D, data=packet)

    def _process_receptions(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> None:
        current_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_D2D)
        if not current_receptions:
            return

        # we process each packet as it is received so only one packet is there at a time
        frame = cast(LoRaD2DFrame, current_receptions[0].data)
        match frame.type:
            case LoRaD2DFrameType.CURRENT_HOP_COUNT:
                self._process_current_hopcount(frame, current_local_clock_info.current_local_time)

            case LoRaD2DFrameType.DATA_TO_GW:
                if self.node_id in frame.destination_node_id:
                    self.rx_buffer.append(frame)

            case LoRaD2DFrameType.DATA_FROM_GW:
                if self.node_id in frame.destination_node_id:
                    self.rx_buffer.append(frame)

            case LoRaD2DFrameType.REQ_HOP_ACK:
                if self.node_id in frame.destination_node_id:
                    self._process_req_hop_ack(frame, current_local_clock_info.current_local_time)

            case LoRaD2DFrameType.HOP_ACK:
                # we have been ACKed,  we can assume discovery complete
                if self.node_id in frame.destination_node_id:
                    self.discovery_state = DiscoverStates.DISCOVERED
                    self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} discovery complete with hop count {self.hopcount_to_gateway}")

            case LoRaD2DFrameType.CHANGE_HOP_COUNT:
                # we have been instructed to change our hop count, update our hop count to the instructed hop count
                # implied ACk, we can assume discovery complete
                if self.node_id in frame.destination_node_id:
                    self.discovery_state = DiscoverStates.DISCOVERED
                    frame_hop_cnt = cast(PayloadHopCnt, frame.payload)                    
                    self._update_local_hopcount(frame_hop_cnt.cnt)
                    self.own_tx_slot = frame_hop_cnt.use_slot
                    self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} discovery complete with hop count {self.hopcount_to_gateway}")

        # update last seen for neighbor
        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing:
            if existing.last_seen < self.slot_period_start:
                existing.first_tx_start_time_in_period = current_local_clock_info.current_local_time - self.duration_calculator.get_duration(frame.length)

            existing.last_seen = current_local_clock_info.current_local_time
            existing.last_rssi = frame.rssi
            if self.current_slot > -1:
                existing.in_slot = self.current_slot

    def _process_current_hopcount(self, frame: LoRaD2DFrame, current_local_time: int) -> None:
        frame_hop_cnt = cast(PayloadHopCnt, frame.payload)

        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing is None:
            neighbor_info = D2DNeighborInfo(
                neighbor_id=frame.source_node_id, 
                hopcount_to_gateway=frame_hop_cnt.cnt, 
                last_seen=current_local_time, 
                last_rssi=frame.rssi,
                in_slot=frame_hop_cnt.use_slot)
            self.known_neighbors.append(neighbor_info)
        else:
            existing.hopcount_to_gateway = frame_hop_cnt.cnt

    def _process_req_hop_ack(self, frame: LoRaD2DFrame, current_local_time: int) -> None:

        # TODO: handle edge case where we have more neighbors than slots...

        def get_slot_for_neighbor(neighbor: D2DNeighborInfo) -> int:
            if neighbor.in_slot != -1:
                return neighbor.in_slot

            # find new slot
            used_slots = {n.in_slot for n in self.known_neighbors if n.in_slot > -1}
            used_slots.add(self.own_tx_slot)
            usable = {range(1, self.slot_count)}

            available = usable.difference(used_slots)
            return available[0] if available else 0

        frame_hop_cnt = cast(PayloadHopCnt, frame.payload)

        validate_hopcount = frame_hop_cnt.cnt

        # find requesting node in known neighbors and update hop count if needed
        neighbor = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if neighbor is None:
            neighbor = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=validate_hopcount, last_seen=current_local_time, last_rssi=frame.rssi, in_slot=-1)
            self.known_neighbors.append(neighbor)
        elif neighbor.hopcount_to_gateway != validate_hopcount:
            neighbor.hopcount_to_gateway = validate_hopcount
            neighbor.last_rssi = frame.rssi

        # order list by lowest hopcount then by best RSSI
        self.known_neighbors.sort(key=lambda x: (x.hopcount_to_gateway, -x.last_rssi))

        # only iterate on neighbors with higher hopcount than own
        of_interest = (neighbor for neighbor in self.known_neighbors if neighbor.hopcount_to_gateway > self.hopcount_to_gateway)
        current_hop = self.hopcount_to_gateway
        prev_rssi = 0
        rssi_threshold = 6
        for neighbor in of_interest:
            if abs(prev_rssi - neighbor.last_rssi) > rssi_threshold:
                prev_rssi = neighbor.last_rssi
                current_hop += 1 # increment by one for each "layer"

            if neighbor.hopcount_to_gateway == current_hop:
                continue # no chaange

            neighbor.hopcount_to_gateway = current_hop
            in_slot = get_slot_for_neighbor(neighbor)
            change_frame = LoRaD2DFrame(source_node_id=self.node_id, destination_node_id={neighbor.neighbor_id}, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=PayloadHopCnt(cnt=current_hop, use_slot=in_slot))
            change_frame.crc_calc()

            existing_frame_index = next((i for i, f in enumerate(self.tx_buffer) if neighbor.neighbor_id in f.destination_node_id and f.type in [LoRaD2DFrameType.CHANGE_HOP_COUNT, LoRaD2DFrameType.HOP_ACK]), None)
            if existing_frame_index is not None:
                self.tx_buffer[existing_frame_index] = change_frame
            else:
                self.tx_buffer.append(change_frame)

        # multiple can have same hop count... if the RSSI are within 3dB of each other
        # if more the lower rsssi have +1 hopcount
        # we need to find tx slot available
        


    def _update_local_hopcount(self, hopcount: int) -> None:
        self.hopcount_to_gateway = hopcount
        self.own_tx_slot = 1 # default zero is reserved for REQ_ACK unit 17 slots are needed
