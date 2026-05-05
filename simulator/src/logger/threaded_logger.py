# type: ignore
import threading
from typing import Any, List

from custom_types import Area, LogMessage, Severity
from logger.ILogger import ILogger


class ThreadedLogger(ILogger):
	"""Logger that flushes messages asynchronously using EventNet objects.

	The public API mirrors SimpleLogger except that "add" accepts the
	same parameters as EventNet and stores EventNet instances in the
	buffer.  Flushing happens in a background thread; overlapping flush
	requests are ignored.
	"""

	def __init__(self, log_path: str, buffer_size: int = 10) -> None:
		self.log_path = log_path
		self.buffer_size = buffer_size
		self._buffer: List[LogMessage] = []
		self._first_flush_done = False
		self._flush_lock = threading.Lock()
		self._thread: threading.Thread | None = None

	def add(self, severity: Severity, area: Area, global_time: int, info: str, data: Any = None) -> None:
		logentry = LogMessage(global_time, severity, area, info, data)
		self._buffer.append(logentry)

	def flush(self, force: bool = False) -> bool:
		if not (force or len(self._buffer) >= self.buffer_size):
			return False

		# if non-forced flush and a flush is in progress, ignore
		if not force and self._flush_lock.locked():
			return False

		# if force, wait for any running flush to finish
		if force:
			while self._flush_lock.locked():
				threading.Event().wait(0.001)

		to_write = self._buffer.copy()
		self._buffer.clear()

		def worker(logs: List[LogMessage]):
			with self._flush_lock:
				with open(self.log_path, "a", encoding="utf-8", buffering=self.buffer_size) as f:
					if not self._first_flush_done:
						f.write("--- threaded logger start ---\n")
						self._first_flush_done = True
					for log in logs:
						f.write(f"[{log.severity.value}] ({log.area.value}) @ {log.global_time}: {log.info}, {log.data if log.data else ''}\n")
					f.flush()

		self._thread = threading.Thread(target=worker, args=(to_write,), daemon=True)
		self._thread.start()
		# if force was requested, block until worker finished to ensure persistence
		if force:
			self._thread.join()
		return True
