from collections import deque
from typing import Deque
from ..custom_types import EventNet

class GlobalEventQueue():

    def __init__(self) -> None:
        self.queue: Deque[EventNet] = deque()

    def get_events(self, time_start: int = None, time_end: int = None, as_json: bool = False) -> list:
        if time_start is not None and time_end is not None:
            events = [event for event in self.queue if event.time_start <= time_end and event.time_end >= time_start]
        elif time_start is not None:
            events = [event for event in self.queue if event.time_start <= time_start <= event.time_end]
        elif time_end is not None:
            events = [event for event in self.queue if event.time_start <= time_end <= event.time_end]
        else:
            events = list(self.queue)
        if as_json:
            return [event.model_dump() for event in events]
        return events

    def get_events_start(self, as_json: bool = False) -> EventNet:
        event = self.queue[0]
        if as_json:
            return event.model_dump()
        return event

    def get_events_end(self, as_json: bool = False) -> EventNet:
        event = self.queue[-1]
        if as_json:
            return event.model_dump()
        return event

    def pop_event_start(self, as_json: bool = False) -> EventNet:
        event = self.queue.popleft()
        if as_json:
            return event.model_dump()
        return event

    def pop_event_end(self, as_json: bool = False) -> EventNet:
        event = self.queue.pop()
        if as_json:
            return event.model_dump()
        return event

    def push_event_start(self, event: EventNet):
        self.queue.appendleft(event)

    def push_event_stop(self, event: EventNet):
        self.queue.append(event)

    def sort_queue_time_start(self):
        self.queue = deque(sorted(self.queue, key=lambda event: event.time_start))

def main():
    pass

if __name__ == "__main__":
    main()
