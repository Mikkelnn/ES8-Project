from sortedcontainers import SortedDict


class DeviceEventQueue:
	def __init__(self):
		self.events: SortedDict = SortedDict()

	def init_tick(self, start_tick: int, node_ids: list[int]) -> None:
		self.events = SortedDict({start_tick: set(node_ids)})

	def add_event(self, node_id: int, tick: int | None) -> None:
		if tick is not None:
			self.events.setdefault(tick, default=set()).add(node_id)

	def get_next_events(self) -> tuple[int, list[int]]:
		return self.events.popitem(0)
