
from custom_types import LocalEventTypes, MediumTypes, TranceiverState, Severity, Area
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue
from simulator.logger import Logger

# log = Logger()

class PingPongProtocol(IModule):
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick

    def tick(self, current_global_tick: int) -> float:    
        current_tranceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data # Always populated by tranceiver service before this protocol is ticked, so we can be sure to have it.
        curretnt_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA)

        if self.node_id % 2 == 1 and current_global_tick == 1:
            # We want to start the protocol by sending a ping from node 1 to node 2 at the first global tick, we can be sure that all nodes have been ticked at least once and have set their tranceiver status in the local event queue.
            self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_D2D, data=[1]) # The content of the message does not matter in this protocol, so we just send a list with one element.
            # log.add(Severity.INFO, Area.NODE, f"Node {self.node_id} sent a message at global tick {current_global_tick}...")
            return (0, None) # Power consumption for this tick

        match current_tranceiver_states[MediumTypes.LORA_D2D]:
            case TranceiverState.IDLE:
                # set tranceiver to receiving as we have finished sending in the last tick and we want to be able to receive the pong
                self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TranceiverState.RECEIVING)
            case TranceiverState.RECEIVING:
                if curretnt_receptions:
                    # We have received a message, we want to send a response back
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TranceiverState.IDLE) # Set state to idle before transmitting, so we can receive the next message in the next tick
                    self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_D2D, data=[1]) # The content of the message does not matter in this protocol, so we just send a list with one element.
                    # log.add(Severity.INFO, Area.NODE, f"Node {self.node_id} received a message at global tick {current_global_tick}, sending response...")
            case TranceiverState.TRANSMITTING:
                pass # We don't need to do anything while transmitting, we will set the state to idle

        return (0, None) # Power consumption for this tick

    def reset(self, current_global_tick: int) -> None:
        pass