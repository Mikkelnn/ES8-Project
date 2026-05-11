# type: ignore
from collections import defaultdict

from pyparsing import cast

from custom_types import Area, LocalEventTypes, MediumTypes, Severity, TransceiverState
from Interfaces import IDevice
from logger import ILogger
from loraWanFrameHelper import LoRaWanPHYPayload, make_downlink_ack
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.helpers.accumulated_state import AccumulatedState
from node.transceiver.transceiver_service import TransceiverService
from payload_types import MegaSync, MegaSyncReq


class Gateway(IDevice):
    def __init__(self, gateway_id: int, second_to_global_tick: float, medium_service: MediumService, log: ILogger):
        self.gateway_id = gateway_id
        self.log = log
        self.local_event_queue = LocalEventQueue()
        self.accumulated_state = AccumulatedState()

        self.transceiver = TransceiverService(self.gateway_id, medium_service, self.local_event_queue, second_to_global_tick, log)
        self.second_to_global_tick = second_to_global_tick
        self.rx_at_tick: dict[int, list[LoRaWanPHYPayload]] = defaultdict(list)

    def tick(self, current_global_tick: int) -> int | None:
        self.accumulated_state.reset()

        self.accumulated_state.update(self.transceiver.tick(current_global_tick))

        tranceiver_statuses = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data
        if tranceiver_statuses[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)

        rx_now = self.rx_at_tick.pop(current_global_tick, [])
        if rx_now:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)

        for frame in rx_now:
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=frame)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} sent a response to node {frame.mac_payload.dev_addr} at global tick {current_global_tick} GUID={frame.mac_payload.frm_payload.guid}")

        # Received data
        received_data = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN)
        for event in received_data:
            data = cast(LoRaWanPHYPayload, event.data)
            self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} received data:{data}, GUID={data.mac_payload.frm_payload.guid}")
            rx1_tick = current_global_tick + 1 * (1 / self.second_to_global_tick)  # 1 second after rx as per LoRaWAN specification for rx1
            if data.is_ack():
                pass  # we should send ACK with no payload but this is not currently possible...
                # self.rx_at_tick.setdefault(rx1_tick, []).append(make_downlink_ack(data.mac_payload.dev_addr, frame_count=0, ))
            elif data.mac_payload and isinstance(MegaSyncReq, data.mac_payload.frm_payload):
                frame = make_downlink_ack(dev_addr=data.mac_payload.dev_addr, frame_count=0, payload=MegaSync(time=current_global_tick))
                self.rx_at_tick.setdefault(rx1_tick, []).append(frame)

        if self.rx_at_tick:
            earliest_rx_tick = min(self.rx_at_tick.keys())
            self.accumulated_state.update((0, earliest_rx_tick))

        # Clear local event bus
        self.local_event_queue.clear_events()

        # determine earliest next tick among modules
        # if there are internal events scheduled for next tick, this is the earliest
        return self.accumulated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
