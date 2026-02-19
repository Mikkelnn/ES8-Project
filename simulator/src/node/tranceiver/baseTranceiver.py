from enum import Enum
from typing import List
from simulator.src.custom_types import EventNet, LocalEventTypes
from simulator.src.node.Imodule import IModule
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.simulator import event_net_queue

class TranceiverState(Enum):
    IDLE = 0
    SENDING = 1
    RECEIVING = 2

class BaseTranceiver(IModule):
    def __init__(self, node_id: int, global_event_queue: event_net_queue, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.__node_id = node_id
        self.__global_event_queue = global_event_queue
        self.__local_event_queue = local_event_queue
        self.__second_to_global_tick = second_to_global_tick

        self.state = TranceiverState.IDLE
        self.__current_transmission_end_global_tick = 0
        self.__current_reception_start_global_tick: int | None = None
        self.__receive_queue: List[EventNet] = [] # TODO: simulator should fill this queue....

        self.__joules_per_second_consumption_transmit = 1 # TODO: Set realistic value
        self.__joules_per_second_consumption_receive = 0.5 # TODO: Set realistic value
        self.__joules_per_second_consumption_idle = 0.1 # TODO: Set realistic value

        self.__consuption_per_tick_transmit = self.__joules_per_second_consumption_transmit * second_to_global_tick
        self.__consuption_per_tick_receive = self.__joules_per_second_consumption_receive * second_to_global_tick
        self.__consuption_per_tick_idle = self.__joules_per_second_consumption_idle * second_to_global_tick

    def tick(self, current_global_tick):
        self.__housekeep_receive_queue(current_global_tick)

        state_change = self.__local_event_queue.get_current_events_by_type(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=None) # TODO: Maybe we want to specify sub_type for different protocols?
        transmit_data_events = self.__local_event_queue.get_current_events_by_type(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=None) # TODO: Maybe we want to specify sub_type for different protocols?

        if self.state == TranceiverState.IDLE:
            # Check if we should start transmitting or receiving based on events in the global event queue
            pass

        if self.state == TranceiverState.SENDING:
            # Check if we have finished transmitting
            if current_global_tick >= self.__current_transmission_end_global_tick:
                self.__current_transmission_end_global_tick = 0
                self.state = TranceiverState.IDLE
        
        if self.state == TranceiverState.RECEIVING:
            received_events = self.__get_successful_receptions(current_global_tick)
            for event in received_events:
                self.__local_event_queue.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, event.data, sub_type=None) # TODO: Maybe we want to specify sub_type for different protocols?

        match self.state:
            case TranceiverState.IDLE:
                return self.__consuption_per_tick_idle
            case TranceiverState.SENDING:
                return self.__consuption_per_tick_transmit 
            case TranceiverState.RECEIVING:
                return self.__consuption_per_tick_receive
    
    def reset(self, current_global_tick):
        self.__cancel_transmission(current_global_tick) # Cancel any ongoing transmission
        self.state = TranceiverState.IDLE        
        self.__current_reception_start_global_tick = None
        return
    
    def __cancel_transmission(self, current_global_tick):
        # Logic to determine if a transmission can be cancelled (e.g., if the node dies during transmission)
        if self.state != TranceiverState.SENDING:
            return False # No transmission to cancel
        
        self.__global_event_queue.push_event_stop(EventNet(self.node_id, current_global_tick, self.__current_transmission_end_global_tick, data=None, type="transmit_cancelled"))
        self.__current_transmission_end_global_tick = 0
        self.state = TranceiverState.IDLE

    def __housekeep_receive_queue(self, current_global_tick):        
        # If the event is still ongoing, we keep it in the receive queue. 
        # If it has ended and we are not currently receiving, we remove it from the receive queue.
        for event in reversed(self.__receive_queue): # Iterate in reverse to safely remove items from the list while iterating
            if event.time_end <= current_global_tick and self.__current_reception_start_global_tick is None:
                self.__receive_queue.remove(event)

    def __get_successful_receptions(self, current_global_tick) -> List[EventNet]:
        # Select events that are successful according to rules:
        # - event.time_end must have passed (time_end <= current_global_tick)
        # - __current_reception_start_global_tick (if set) must be before event.time_start
        # - if a cancellation packet exists for the same node_id in __receive_queue, the
        #   original event is NOT successful (match cancellations by node_id)
        # - overlapping events make the event unsuccessful. However, if an overlapping
        #   event has a cancellation whose original end_time is after the candidate's
        #   start_time, treat that cancellation's start time as the overlapping event's
        #   effective end time when checking for overlap.

        successful_receptions: List[EventNet] = []
        if self.__current_reception_start_global_tick is None:
            return successful_receptions # No events can be successful if reception is not started

        # Gather cancellation events from the receive queue (do not consult global queue)
        cancellations = [e for e in self.__receive_queue if getattr(e, "type", None) == "transmit_cancelled"]
        canc_by_node: dict[int, List[EventNet]] = {}
        for c in cancellations:
            canc_by_node.setdefault(c.node_id, []).append(c)

        for event in self.__receive_queue:
            # ignore cancellation entries themselves
            if getattr(event, "type", None) == "transmit_cancelled":
                continue

            # event end must have passed
            if event.time_end > current_global_tick:
                continue

            # ensure reception start (if any) is before this event's start
            if self.__current_reception_start_global_tick is not None and self.__current_reception_start_global_tick > event.time_start:
                continue

            # if any cancellation exists for this event's node_id, it's not successful
            if event.node_id in canc_by_node:
                continue

            # check for overlaps with other (non-cancellation) events
            overlap_found = False
            for other in self.__receive_queue:
                if other is event:
                    continue
                if getattr(other, "type", None) == "transmit_cancelled":
                    continue

                # compute effective end for the other event, considering cancellations
                other_effective_end = other.time_end
                for c in canc_by_node.get(other.node_id, []):
                    # if the cancellation's original end_time is after this candidate's start,
                    # treat the cancellation start as the other packet's effective end
                    if c.time_end > event.time_start:
                        other_effective_end = min(other_effective_end, c.time_start)

                # Determine overlap between [other.time_start, other_effective_end]
                if other.time_start <= event.time_end or other_effective_end >= event.time_start:
                    overlap_found = True
                    break

            if not overlap_found:
                successful_receptions.append(event)
        
        # It should be safe to only keep events whose start_time is after the largest time_end among successful receptions.
        # Find the largest time_end among successful receptions
        max_time_end = 0
        for event in successful_receptions:
            max_time_end = max(max_time_end, event.time_end)

        # Keep events whose time_start is after max_time_end
        self.__receive_queue = [e for e in self.__receive_queue if e.time_start > max_time_end]

        return successful_receptions