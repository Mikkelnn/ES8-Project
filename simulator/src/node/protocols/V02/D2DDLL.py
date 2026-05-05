from dataclasses import dataclass
from typing import List, cast

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaD2DFrame, LoRaD2DFrameType, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue


@dataclass
class D2DNeighborInfo:
	neighbor_id: int
	hopcount_to_gateway: int
	last_seen: int


class D2DDLL:
    DISCOVERY_TIMEOUT_MS = 60_000 + 10 * 1000

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger, slot_duration: int = 100, slot_count: int = 5):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.slot_duration = slot_duration
        self.slot_count = slot_count
        self.current_slot = -1
        self.current_tx_slot = -1
        self.reset(0)


    def reset(self, current_global_tick: int) -> None:
        self.hopcount_to_gateway = 65535
        self.known_neighbors: List[D2DNeighborInfo] = []
        self.discovery_started = False
        self.tx_buffer: List[LoRaD2DFrame] = []
        self.rx_buffer: List[LoRaD2DFrame] = []
        self.current_slot = -1
        self.current_tx_slot = -1

    @property
    def link_established(self) -> bool:
        return self.hopcount_to_gateway < 65535
    
    def set_has_gateway_link(self) -> None:
        if self.hopcount_to_gateway == 65535:
            self.hopcount_to_gateway = 0

    def enqueue_payload(self, payload: bytes) -> None:
        self.tx_buffer.append(
            LoRaD2DFrame(
                source_node_id=self.node_id,
                destination_node_id=0xFFFFFFFF, # TODO: set destination to next hop instead of broadcast
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
        )

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> bool:

        current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data

        if not self.link_established:
           return self._run_discovery(current_global_tick, current_local_clock_info)
        
        # add idle packet -> used for discovery
        if not self.tx_buffer and self.link_established:
            self.tx_buffer.append(LoRaD2DFrame(source_node_id=self.node_id, destination_node_id=0xFFFFFFFF, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=self.hopcount_to_gateway.to_bytes(2, "big")))

        period_finished = self._advance_slot(current_local_clock_info)
        self._run_slot(current_global_tick, current_local_clock_info, current_transceiver_states)

        # process receptions and update neighbors, conflicting hop count info is resolved by taking the lowest hop count + 1 as our hop count
        self._process_receptions(current_global_tick, current_local_clock_info)

        return period_finished

    def _run_discovery(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> None:
        if self.link_established:
            return

        if not self.discovery_started:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.DISCOVERY_TIMEOUT_MS)
            self.discovery_started = True
            self.log.add(Severity.INFO, Area.PROTOCOL, current_global_clock if (current_global_clock := current_global_tick) else current_global_tick, f"Node {self.node_id} started D2D discovery")

            hopcounts = {neighbor.hopcount_to_gateway for neighbor in self.known_neighbors}
            if len(hopcounts) >= 2:
                for hopcount in hopcounts:
                    if (hopcount + 1) in hopcounts:
                        self.hopcount_to_gateway = hopcount + 2
                        # TODO: REQ ACK 
                        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway {self.hopcount_to_gateway} from neighbors")
                        break

        timer_1 = current_local_clock_info.timer_1_remaining
        if timer_1 is not None and timer_1 <= 0 and not self.link_established:
            if len(self.known_neighbors) == 1 and self.known_neighbors[0].hopcount_to_gateway == 0:
                self.hopcount_to_gateway = 1
                self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set hopcount to gateway 1 based on single neighbor")

            self.discovery_started = False

        # Handle case where no ACK is received in next period
        # We need to retry ACK in new random mini-slot in the next period to avoid collisions with other nodes retrying at the same time

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> bool:
        if not self.link_established:
            return False

        timer_1 = current_local_clock_info.timer_1_remaining
        if timer_1 is None or timer_1 == 0:
            self.current_slot += 1
            if self.current_slot < self.slot_count:
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.slot_duration)
                if self.current_slot == self.current_tx_slot:
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_2, data=10)
                return False

            self.current_slot = -1
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
            return True

        return False

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
                self.rx_buffer.append(frame)

            case LoRaD2DFrameType.DATA_FROM_GW:
                self.rx_buffer.append(frame)

            case LoRaD2DFrameType.REQ_HOP_ACK:
                # determine if we can ACK -> no neighbor should have it
                # if two neighbors have same hop count, we have to change their hop counts to avoid collisions
                # use RSSI to determine closest neighbor and ACK that one, for the other we will change their hop count to our hop count + 1 and send a CHANGE_HOP_COUNT instructing them to change their hop count
                pass

            case LoRaD2DFrameType.HOP_ACK:
                # we have been ACKed,  we can assume discovery complete                
                pass

            case LoRaD2DFrameType.CHANGE_HOP_COUNT:
                # we have been instructed to change our hop count, update our hop count to the instructed hop count
                # implied ACk, we can assume discovery complete
                pass
        
        # update last seen for neighbor
        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing:
            existing.last_seen = current_local_clock_info.current_local_time

    def _process_current_hopcount(self, frame: LoRaD2DFrame, current_local_time: int) -> None:
        hopcount = int.from_bytes(frame.payload, "big")

        existing = next((n for n in self.known_neighbors if n.neighbor_id == frame.source_node_id), None)
        if existing is None:
            neighbor_info = D2DNeighborInfo(neighbor_id=frame.source_node_id, hopcount_to_gateway=hopcount, last_seen=current_local_time)
            self.known_neighbors.append(neighbor_info)
        else:
            existing.hopcount_to_gateway = hopcount
            existing.last_seen = current_local_time
        

