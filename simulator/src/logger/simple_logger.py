from custom_types import Area, Severity
from logger.ILogger import ILogger
from typing import Any, List


class SimpleLogger(ILogger):
    """Lightweight logger that buffers messages and flushes them to a file.

    The class keeps only the *pending* buffer in memory.  Once the buffer is
    flushed it is written directly to disk and discarded.  A special "start"
    message is written the first time a flush occurs.
    """

    def __init__(self, log_path: str, buffer_size: int = 10) -> None:
        """Create a logger.

        Parameters
        ----------
        log_path:
            Path to the file in which flushed messages will be appended.
        buffer_size:
            Number of messages to accumulate before an automatic flush.
        """

        self.log_path = log_path
        self.buffer_size = buffer_size
        self._buffer: List[str] = []
        self._first_flush_done = False

    def add(self, severity: Severity, area: Area, global_time: int, info: str, data: Any = None) -> None:
        formatted = f"[{severity.value}] ({area.value}) @ {global_time}: {info}, {data if data else ''}"
        self._buffer.append(formatted + '\n')

    def get(self) -> List[str]:
        """Get log buffer"""
        tmp_buffer = self._buffer

        return tmp_buffer

    def flush(self, force: bool = False) -> bool:
        """Write buffered messages to the log file.

        Parameters
        ----------
        force:
            If ``True`` flush regardless of buffer length.

        Returns
        -------
        bool
            ``True`` if a flush occurred, ``False`` otherwise.
        """

        if not (force or len(self._buffer) >= self.buffer_size):
            return False

        with open(self.log_path, "a", encoding="utf-8", buffering=self.buffer_size) as f:
            # first flush header
            if not self._first_flush_done:
                f.write("--- logger start ---\n")
                self._first_flush_done = True
            f.writelines(self._buffer)
            f.flush()

        self._buffer.clear()
        return True