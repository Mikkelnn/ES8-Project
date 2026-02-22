from typing import List, Any
from custom_types import LocalEventNet, LocalEventSubTypes, LocalEventTypes, TranceiverState

class LocalEventQueue:
    def __init__(self):        
        self.current_events: List[LocalEventNet] = []
        self.next_tick_events: List[LocalEventNet] = []
    
    """ Only modules called after in this global tick can see the event. """
    def add_event_to_current_tick(self, type: LocalEventTypes, data: Any, sub_type: LocalEventSubTypes | None = None):
        self.current_events.append(LocalEventNet(type=type, sub_type=sub_type, data=data))
    
    """ Only modules called in the next global tick can see the event. """
    def add_event_to_next_tick(self, type: LocalEventTypes, data: Any, sub_type: LocalEventSubTypes | None = None):
        self.next_tick_events.append(LocalEventNet(type=type, sub_type=sub_type, data=data))

    def get_all_current_events(self) -> List[LocalEventNet]:
        return self.current_events
    
    def get_current_events_by_type(self, type: LocalEventTypes, sub_type: LocalEventSubTypes | None = None) -> List[LocalEventNet]:
        return [event for event in self.current_events if event.type == type and (event.sub_type == sub_type or sub_type is None)]
    
    def clear_events(self):
        self.current_events = self.next_tick_events
        self.next_tick_events = []
    
    def reset(self):
        self.current_events = []
        self.next_tick_events = []