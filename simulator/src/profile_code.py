# type: ignore
import time

from custom_types import Area, NodeMediumInfo, Severity
from logger import ILogger
from logger.simple_logger import SimpleLogger
from medium.medium_service import MediumService
from node.node import Node
from sim.device_event_queue import DeviceEventQueue
from sim.global_time import GlobalTime


class TestEngine:
	def initialize_nodes(self):

		# make N nodes that ping pong in pairs and have the other as neighbor, for testing purposes
		num_nodes = 10_000
		node_neighbors = {}

		self.nodes: list[Node] = []
		self.log: ILogger = SimpleLogger(log_path="profile-results.log", buffer_size=100_000)
		self.global_time = GlobalTime()
		self.event_queue = DeviceEventQueue()
		self.event_queue.init_tick(start_tick=1, node_ids=range(1, num_nodes + 1))

		for i in range(1, num_nodes + 1):
			neighbors = []
			if i % 2 == 1 and i < num_nodes:  # Odd node, add next node as neighbor
				neighbors.append(i + 1)
			elif i % 2 == 0:  # Even node, add previous node as neighbor
				neighbors.append(i - 1)
			node_neighbors[i] = NodeMediumInfo(position=(i, 0), neighbors=neighbors, gateways_in_range=[])

		self.medium_service = MediumService(node_neighbors=node_neighbors, event_queue=self.event_queue, log=self.log)

		for i in range(1, num_nodes + 1):
			self.nodes.append(Node(node_id=i, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))

	def run_for(self, stop_tick):
		stopwatch_start_time = time.time()
		propagation_time = 0
		node_tick_time = 0

		current_time = 0
		total_evaluated = 0
		while len(self.event_queue.events):
			(current_time, node_ids) = self.event_queue.get_next_events()
			self.global_time.set_time(current_time)
			if current_time > stop_tick:
				current_time = stop_tick
				break

			# Tick all nodes, do this in parallel if needed
			node_start_time = time.time()
			for node_id in node_ids:
				next_evaluation = self.nodes[node_id - 1].tick(current_time)
				self.event_queue.add_event(node_id, next_evaluation)

			node_tick_time += time.time() - node_start_time

			propagation_start_time = time.time()
			self.medium_service.propagate_mediums(current_time)  # propagate all new transmissions in the mediums and handle receptions
			propagation_time += time.time() - propagation_start_time
			total_evaluated += 1

			self.log.flush()

		elapsed_time = time.time() - stopwatch_start_time

		self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total elapsed real time: {elapsed_time:.2f} seconds for {len(self.nodes)} nodes")
		self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total node tick time: {node_tick_time:.2f} seconds")
		self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total propagation time: {propagation_time:.2f} seconds")
		self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total log time: {(elapsed_time - (propagation_time + node_tick_time)):.2f} seconds")
		self.log.flush(force=True)


if __name__ == "__main__":
	engine = TestEngine()
	engine.initialize_nodes()
	engine.run_for(10_000)

	# with cProfile.Profile() as profile:

	# results = pstats.Stats(profile)
	# results.sort_stats(pstats.SortKey.TIME)
	# results.print_stats()
	# results.dump_stats("results.prof")
