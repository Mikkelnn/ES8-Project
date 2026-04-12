
from dataclasses import dataclass
from enum import Enum

from pyparsing import cast
from custom_types import LocalEventTypes, MediumTypes, TransceiverState, Severity, Area
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue
from logger.ILogger import ILogger
from loraWanFrameHelper import LoRaWanPHYPayload, make_uplink

class State(Enum):
    INITIAL = 0
    SKIP_NEXT_TICK = 1 # used to skip next tick when  sleeping is scheduled, set the stae here to the one that should be executed after waking up

    TRY_CONNECT_GATEWAY = 2
    GATEWAY_TX_WAIT_COMPLETE = 3
    GATEWAY_RX = 4

    D2D_SYNC = 5
    D2D_RX = 6
    D2D_TX_WAIT_COMPLETE = 7

@dataclass
class D2DNeighborInfo:
    neighbor_id: int
    hopcount_to_gateway: int
    last_seen: int # local time when we last saw this neighbor, used to remove stale neighbors from the known_neighbors list after some time

class V01(IModule):
    "This implement simple WAN GW discovery and a simple D2D hopcount establishment."

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick
        self.log = log

        self.reset(0)
        

    def tick(self, current_global_tick: int) -> float:
        current_local_time = self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)[0].data
        current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data # Always populated by transceiver service before this protocol is ticked, so we can be sure to have it.
        current_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA)

        match self.state:
            case State.INITIAL:
              # set to sleep for 45 min to ensure battery is charged.
              sleep_duration_milliseconds = 45 * 60 * 1000
              self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, sub_type=None, data=sleep_duration_milliseconds)
              self.state = State.TRY_CONNECT_GATEWAY

            case State.SKIP_NEXT_TICK:
                self.state = self.next_state
                self.next_state = None

            case State.TRY_CONNECT_GATEWAY:
                # try to connect to gateway by sending a message on the LoRaWAN channel, we will not do anything with the response in this simple protocol, we just want to test that we can send and receive messages on the LoRaWAN channel and that the gateway can respond.
                lora_wan_frame = make_uplink(dev_addr=self.node_id, frame_count=0, payload=[], confirmed=True) # The content of the message does not matter in this protocol, so we just send a list with one element.)
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=lora_wan_frame)
                self.state = State.GATEWAY_TX_WAIT_COMPLETE

            case State.GATEWAY_TX_WAIT_COMPLETE:
                if current_transceiver_states[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
                    self.next_state = State.GATEWAY_RX
                    self.state = State.SKIP_NEXT_TICK
                    # wait for 1 second after tx as per LoRaWAN specification for rx1 and add a small guard time of 10 ms to ensure we do not miss the rx window due to clock drift
                    wait_for_rx = 1000 - 10
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, sub_type=None, data=wait_for_rx)

            case State.GATEWAY_RX:
                if current_transceiver_states[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)
                    self.rx_stop_time = current_local_time + 1000 # Listen for 1 second as per LoRaWAN specification for rx1
                
                if current_local_time >= self.rx_stop_time:
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
                    self.rx_stop_time = None
                    # waht to do now....

                if len(current_receptions) > 0:
                    reception_data = cast(LoRaWanPHYPayload, current_receptions[0].data)
                    if reception_data.mac_payload.mhdr.dev_addr == self.node_id and reception_data.is_ack():
                        self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
                        self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} received ACK from gateway!")
                        # We did receive the ACK from the gateway, we can now set our hopcount to 0 and start doing D2D syncs to establish hopcounts to neighbors.
                        self.gw_hopcount = 0 
                        self.rx_stop_time = None

        # return next tick to evaluate, rx_stop_time to global tick somehow...
        return (0, None) # Power consumption for this tick

    def reset(self, current_global_tick: int) -> None:
        self.state = State.INITIAL
        self.next_state = None
        self.rx_stop_time = None
        # This is the maximum value for a uint16, we use this to indicate that we do not have a connection to the gateway yet. 
        # Once we have a connection to the gateway, we will set this to 0 and start doing D2D syncs to establish hopcounts to neighbors.
        # If we do not receive an ACK from the gateway we try to connect using D2D
        self.gw_hopcount = 65535
        self.known_neighbors: list[D2DNeighborInfo] = []