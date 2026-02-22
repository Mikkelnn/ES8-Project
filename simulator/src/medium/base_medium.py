
from abc import ABC, abstractmethod
from typing import List
from simulator.src.custom_types import EventNet, EventNetTypes, MediumTypes


class BaseMedium(ABC):
    def __init__(self, type: MediumTypes):
        self.type = type

        self.transmit_event_queue: List[EventNet] = []
        self.ongoing_transmissions = {} # key: from_node_id, value: (globaltick_end_transmission, [received node_ids])
        self.node_receptions = {} # key: to_node_id, value: List[EventNet]

    def propagate_queue(self, current_global_tick: int):
        for event in self.transmit_event_queue:
            if event.type == EventNetTypes.CANCELED:
                if event.node_id in self.ongoing_transmissions:
                    cancelled_transmission = self.ongoing_transmissions[event.node_id]
                    del self.ongoing_transmissions[event.node_id] # Remove the ongoing transmission for this node
                    for to_node_id in cancelled_transmission[1]: # For each node that was supposed to receive this transmission, we need to remove the corresponding reception event from their reception queue
                        self.__add_reception_event_for_node(to_node_id, event)

            # TODO: what if a transmission is started before a previous transmission from the same node is cancelled?
            elif event.type == EventNetTypes.TRANSMIT: 
                received_node_ids = self._get_reception_node_ids(event)
                self.ongoing_transmissions[event.node_id] = (event.time_end, received_node_ids)
                for to_node_id in received_node_ids:
                    self.__add_reception_event_for_node(to_node_id, event)
        
        self.transmit_event_queue.clear() # Clear the transmit event queue after processing all events
        self.__housekeep_ongoing_transmissions(current_global_tick)
      
    def __housekeep_ongoing_transmissions(self, current_global_tick: int):
        # Remove any ongoing transmissions that have ended
        for from_node_id, (globaltick_end_transmission, received_node_ids) in list(self.ongoing_transmissions.items()):
            if globaltick_end_transmission <= current_global_tick:
                del self.ongoing_transmissions[from_node_id]
                    
    def __add_reception_event_for_node(self, to_node_id: int, event: EventNet):
        if to_node_id not in self.node_receptions:
            self.node_receptions[to_node_id] = []
        self.node_receptions[to_node_id].append(event)

    @abstractmethod
    def _get_reception_node_ids(self, event: EventNet) -> List[int]:
        pass

    def add_transmission_event(self, event: EventNet):
        self.transmit_event_queue.append(event)
    
    def pop_received_event_for_node(self, to_node_id: int) -> List[EventNet]:
        if to_node_id in self.node_receptions:
            events = self.node_receptions[to_node_id]
            del self.node_receptions[to_node_id] # Clear the reception queue for this node after popping the events
            return events
