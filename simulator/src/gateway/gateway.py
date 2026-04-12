from enum import Enum

from pyparsing import cast

from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.transceiver.transceiver_service import TransceiverService
from node.helpers.accumulated_state import AccumulatedState
from logger import ILogger
from IDevice import IDevice
from custom_types import Area, LocalEventTypes, MediumTypes, Severity, TransceiverState
from loraWanFrameHelper import LoRaWanPHYPayload, make_downlink_ack

class Gateway(IDevice):
    def __init__(self, gateway_id: int, second_to_global_tick: float, medium_service: MediumService, log: ILogger):
        self.gateway_id = gateway_id
        self.log = log
        self.local_event_queue = LocalEventQueue()
        self.accumelated_state = AccumulatedState()

        self.transceiver = TransceiverService(self.gateway_id, medium_service, self.local_event_queue, second_to_global_tick, log)
        self.second_to_global_tick = second_to_global_tick
        self.rx_to_node: tuple[int, int] | None = None

    def tick(self, current_global_tick: int) -> int | None:
        self.accumelated_state.reset()

        self.accumelated_state.update(self.transceiver.tick(current_global_tick))
        
        tranceiver_statuses = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data
        if tranceiver_statuses[MediumTypes.LORA_WAN] == State.IDLE:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)
        
        if self.rx_to_node is not None and current_global_tick >= self.rx_to_node[0]:            
            # The content of the message does not matter in this protocol, so we just send a list with one element.
            (rx1_tick, dev_addr) = self.rx_to_node
            frame = make_downlink_ack(dev_addr=dev_addr, frame_count=0)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=frame)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} sent a response to node {dev_addr} at global tick {current_global_tick}...")
            self.rx_to_node = None

        # Received data
        received_data = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN)
        if len(received_data) > 0:
            data = cast(LoRaWanPHYPayload, received_data[0].data)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} received data:", data)
            rx1_tick = current_global_tick + 1 * (1 / self.second_to_global_tick) # 1 second after rx as per LoRaWAN specification for rx1
            self.rx_to_node = (rx1_tick, data.mac_payload.dev_addr)        

        if self.rx_to_node is not None:
            self.accumelated_state.update((0, self.rx_to_node[0]))

        # Clear local event bus
        self.local_event_queue.clear_events()

        # determine earliest next tick among modules
        # if there are internal events scheduled for next tick, this is the earliest
        return self.accumelated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
