from collections import defaultdict
from typing import Any, List

from custom_types import LocalEventNet, LocalEventSubTypes, LocalEventTypes, MediumTypes


class LocalEventQueue:
    def __init__(self):
        self._current: dict[LocalEventTypes, list] = defaultdict(list)
        self._next: dict[LocalEventTypes, list] = defaultdict(list)

    # Keep legacy attribute name for any code that reads .current_events directly
    @property
    def current_events(self) -> list:
        result = []
        for v in self._current.values():
            result.extend(v)
        return result

    """ Only modules called after in this global tick can see the event. """

    def add_event_to_current_tick(self, type: LocalEventTypes, data: Any, sub_type: MediumTypes | LocalEventSubTypes | None = None) -> None:
        self._current[type].append(LocalEventNet(type=type, sub_type=sub_type, data=data))

    """ Only modules called in the next global tick can see the event. """

    def add_event_to_next_tick(self, type: LocalEventTypes, data: Any, sub_type: MediumTypes | LocalEventSubTypes | None = None) -> None:
        self._next[type].append(LocalEventNet(type=type, sub_type=sub_type, data=data))

    def get_current_events_by_type(self, type: LocalEventTypes, sub_type: MediumTypes | LocalEventSubTypes | None = None) -> List[LocalEventNet]:
        events = self._current.get(type)
        if not events:
            return []
        if sub_type is None:
            return events
        return [e for e in events if e.sub_type == sub_type]

    def clear_events(self):
        self._current = self._next
        self._next = defaultdict(list)

    def reset(self):
        self._current = defaultdict(list)
        self._next = defaultdict(list)

    def have_events(self) -> bool:
        return bool(self._current)
