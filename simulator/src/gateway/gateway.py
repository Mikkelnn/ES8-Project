# type: ignore
from pyparsing import cast

from custom_types import Area, LocalEventTypes, MediumTypes, Severity, TransceiverState
from Interfaces import IDevice
from logger import ILogger
from loraWanFrameHelper import LoRaWanPHYPayload, make_downlink_ack
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.helpers.accumulated_state import AccumulatedState
from node.transceiver.transceiver_service import TransceiverService


class Gateway(IDevice):
    def __init__(self, gateway_id: int, second_to_global_tick: float, medium_service: MediumService, log: ILogger):
        self.gateway_id = gateway_id
        self.log = log
        self.local_event_queue = LocalEventQueue()
        self.accumulated_state = AccumulatedState()

        self.transceiver = TransceiverService(self.gateway_id, medium_service, self.local_event_queue, second_to_global_tick, log)
        self.second_to_global_tick = second_to_global_tick
        self.rx_to_nodes: dict[int, int] = {}

    def tick(self, current_global_tick: int) -> int | None:
        self.accumulated_state.reset()

        self.accumulated_state.update(self.transceiver.tick(current_global_tick))

        tranceiver_statuses = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data
        if tranceiver_statuses[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)

        nodes_to_respond = [dev_addr for dev_addr, rx_tick in self.rx_to_nodes.items() if current_global_tick >= rx_tick]
        for dev_addr in nodes_to_respond:
            frame = make_downlink_ack(dev_addr=dev_addr, frame_count=0)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=frame)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} sent a response to node {dev_addr} at global tick {current_global_tick}...")
            del self.rx_to_nodes[dev_addr]

        # Received data
        received_data = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN)
        for event in received_data:
            data = cast(LoRaWanPHYPayload, event.data)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} received data:", data)
            rx1_tick = current_global_tick + 1 * (1 / self.second_to_global_tick)  # 1 second after rx as per LoRaWAN specification for rx1
            self.rx_to_nodes[data.mac_payload.dev_addr] = rx1_tick

        if self.rx_to_nodes:
            earliest_rx_tick = min(self.rx_to_nodes.values())
            self.accumulated_state.update((0, earliest_rx_tick))

        # Clear local event bus
        self.local_event_queue.clear_events()

        # determine earliest next tick among modules
        # if there are internal events scheduled for next tick, this is the earliest
        return self.accumulated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
