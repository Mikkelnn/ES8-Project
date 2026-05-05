from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.Imodule import IModule
from node.protocols.V02.APP import APP, AppPacket
from node.protocols.V02.D2DDLL import D2DDLL
from node.protocols.V02.DLL import DLL
from node.protocols.V02.WANDLL import WANDLL


class V02(IModule):
	def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
		self.node_id = node_id
		self.local_event_queue = local_event_queue
		self.second_to_global_tick = second_to_global_tick
		self.log = log

		self.app_to_dll_tx: list[AppPacket] = []
		self.dll_to_app_rx: list[AppPacket] = []

		self.app = APP(node_id, local_event_queue, log, self.app_to_dll_tx, self.dll_to_app_rx)
		self.d2d = D2DDLL(node_id, local_event_queue, log)
		self.wan = WANDLL(node_id, local_event_queue, log)
		self.dll = DLL(node_id, local_event_queue, second_to_global_tick, log, self.d2d, self.wan, self.app_to_dll_tx, self.dll_to_app_rx)

    def tick(self, current_global_tick: int) -> tuple[float, int | None]:
        node_sleep_events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_SLEEP)
        if len(node_sleep_events) == 0:
            self.app.tick(current_global_tick)
            self.dll.tick(current_global_tick)

		return 0, None

	def reset(self, current_global_tick: int) -> None:
		self.app.reset(current_global_tick)
		self.d2d.reset(current_global_tick)
		self.wan.reset(current_global_tick)
		self.dll.reset(current_global_tick)
