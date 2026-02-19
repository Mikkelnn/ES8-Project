
class LocalEventBus:
    def __init__(self):        
        self.current_events = []
        self.nextTickEvents = []
    
    """ Only modules called after in this global tick can see the event. """
    def add_event_to_current_tick(self, event):
        self.current_events.append(event)
    
    """ Only modules called in the next global tick can see the event. """
    def add_event_to_next_tick(self, event):
        self.nextTickEvents.append(event)

    def get_events(self):
        return self.current_events
    
    def clear_events(self):
        self.current_events = self.nextTickEvents
        self.nextTickEvents = []
