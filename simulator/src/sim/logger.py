# type: ignore
import asyncio
import multiprocessing
import queue
import threading

# Set multiprocessing start method for cross-platform robustness (avoid fork() warnings)
try:
	multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
	pass
from custom_types import LogMessage


class Logger:
	"""
	Multiprocessing-based singleton logger.
	Use start(), add(), and stop() to manage logging.
	Thread/process safe. High-throughput via batching.
	"""

	@classmethod
	def reset(cls):
		with cls._lock:
			if cls._instance is not None:
				if getattr(cls._instance, "_logger_process", None) is not None:
					try:
						cls._instance.stop()
					except Exception:
						pass
			cls._instance = None

	_instance = None
	_lock = threading.Lock()

	def __new__(cls, log_path: str | None = None):
		with cls._lock:
			if cls._instance is None:
				cls._instance = super(Logger, cls).__new__(cls)
				cls._instance._initialized = False
				cls._instance._log_path_set = None
		return cls._instance

	def __init__(self, log_path: str | None = None):
		if getattr(self, "_initialized", False):
			return
		if log_path is None:
			if self._log_path_set is None:
				raise ValueError("Logger must be initialized with a log_path the first time.")
			log_path = self._log_path_set
		else:
			self._log_path_set = log_path
		self.log_path = log_path
		self._log_queue = None
		self._logger_process = None
		self._initialized = True

	def start(self) -> None:
		if self._logger_process is not None:
			raise RuntimeError("Logger already started.")
		# Use an unbounded queue for non-blocking add()
		self._log_queue = multiprocessing.Queue(maxsize=0)
		# Use a unique string sentinel for stop (object() is not picklable)
		self._STOP_SENTINEL = "__LOGGER_STOP__"
		self._logger_process = multiprocessing.Process(target=self._run_logger, args=(self._log_queue, self.log_path, self._STOP_SENTINEL))
		self._logger_process.start()

	def add(self, log_entry: LogMessage) -> None:
		"""
		Non-blocking: puts log_entry into the logger's buffer immediately.
		"""
		if self._log_queue is None or self._logger_process is None:
			raise RuntimeError("Logger not started.")
		try:
			self._log_queue.put_nowait(log_entry)
		except Exception:
			pass  # Drop log if queue is somehow full (should not happen with maxsize=0)

	def stop(self) -> None:
		if self._log_queue is None or self._logger_process is None:
			return
		# Use the unique sentinel for stop
		self._log_queue.put(self._STOP_SENTINEL)
		self._logger_process.join()
		self._logger_process = None
		self._log_queue = None

	@staticmethod
	def _run_logger(log_queue: multiprocessing.Queue, log_path: str, STOP_SENTINEL) -> None:
		"""
		Logger process: batch log entries and write to disk efficiently.
		Flush immediately on stop, drain queue after stop, and use a unique sentinel.
		"""
		import time

		BATCH_SIZE = 1024 * 10  # Increased for higher throughput
		FLUSH_INTERVAL = 0.0001  # Lower interval for lower latency
		BUFFERING = 1024 * 1024
		buffer = []
		last_flush = time.time()
		# Use larger buffer for file writes
		with open(log_path, "a", encoding="utf-8", buffering=BUFFERING) as f:
			while True:
				try:
					log_entry = log_queue.get(timeout=FLUSH_INTERVAL)
					if log_entry == STOP_SENTINEL:
						break
					buffer.append(str(log_entry) + "\n")
				except queue.Empty:
					pass
				except Exception:
					continue
				now = time.time()
				if buffer and (len(buffer) >= BATCH_SIZE or now - last_flush >= FLUSH_INTERVAL):
					f.writelines(buffer)
					f.flush()
					buffer.clear()
					last_flush = now
			# Drain any remaining logs in the queue after stop
			while True:
				try:
					log_entry = log_queue.get_nowait()
					if log_entry == STOP_SENTINEL:
						continue
					buffer.append(str(log_entry) + "\n")
				except queue.Empty:
					break
			if buffer:
				f.writelines(buffer)
				f.flush()


# Async logger client
class LoggerClientAsync:
	"""
	Asyncio-based logger client.
	Use start(), add(), and stop() for async logging.
	"""

	def __init__(self, log_path: str | None = None):
		# Use a local reference for speed
		self.logger = Logger(log_path) if log_path else Logger._instance
		self._queue = asyncio.Queue()
		self._task = None

	async def start(self) -> None:
		if self._task is None:
			self._task = asyncio.create_task(self._worker())

	async def add(self, log_entry: LogMessage) -> None:
		# Non-blocking put for async client
		try:
			self._queue.put_nowait(log_entry)
		except Exception:
			pass

	async def _worker(self):
		logger = self.logger
		queue = self._queue
		while True:
			log_entry = await queue.get()
			if log_entry == "__STOP_ASYNC__":
				break
			logger.add(log_entry)

	async def stop(self) -> None:
		await self._queue.put("__STOP_ASYNC__")
		if self._task:
			await self._task
			self._task = None


# Persistent sync-to-async logger client


class LoggerClientSync:
	"""
	Sync logger client that wraps LoggerClientAsync for use in non-async code.
	Each instance manages its own thread and async client.
	"""

	def __init__(self, log_path: str | None = None):
		self._queue = queue.Queue()
		self._thread = None
		self._shutdown = threading.Event()
		self._log_path = log_path
		self._started = False
		self._start_thread()

	def _start_thread(self):
		if self._thread is not None:
			return
		self._shutdown.clear()
		queue_ = self._queue
		shutdown = self._shutdown
		log_path = self._log_path

		def run():
			async def main():
				client = LoggerClientAsync(log_path)
				await client.start()
				while True:
					msg = queue_.get()
					if msg == "__STOP_BRIDGED__" or shutdown.is_set():
						break
					await client.add(msg)
				await client.stop()

			asyncio.run(main())

		self._thread = threading.Thread(target=run, daemon=True)
		self._thread.start()
		self._started = True

	def add(self, log_entry: LogMessage) -> None:
		if not self._started:
			self._start_thread()
		if not isinstance(log_entry, LogMessage):
			raise TypeError("LoggerClientSync.add() only accepts LogMessage objects.")
		try:
			self._queue.put_nowait(log_entry)
		except Exception:
			pass

	def stop(self) -> None:
		if self._thread is None:
			return
		self._shutdown.set()
		self._queue.put("__STOP_BRIDGED__")
		self._thread.join()
		self._thread = None
		self._started = False
