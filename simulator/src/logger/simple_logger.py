# type: ignore
import inspect
import os
from typing import Any, List, Tuple

from custom_types import Area, Severity
from logger.ILogger import ILogger


class SimpleLogger(ILogger):
    """Lightweight logger that buffers messages and flushes selected severities."""

    _log_caller_filename = False  # BEWARE, performance killer

    # Explicit severity ranking
    _severity_order = {
        Severity.DEBUG: 0,
        Severity.INFO: 1,
        Severity.WARNING: 2,
        Severity.ERROR: 3,
        Severity.CRITICAL: 4,
    }

    def __init__(
        self,
        log_path: str,
        buffer_size: int = 10,
        flush_min_severity: Severity = Severity.INFO,
    ) -> None:
        """
        Parameters
        ----------
        log_path:
            File path to append logs to.

        buffer_size:
            Number of messages before automatic flush.

        flush_min_severity:
            Minimum severity written to file during flush.
            Default = INFO.
        """

        self.log_path = log_path
        self.buffer_size = buffer_size
        self.flush_min_severity = flush_min_severity

        # Stores ALL messages in memory
        self._buffer: List[Tuple[Severity, str]] = []

        self._first_flush_done = False

    @classmethod
    def enable_caller_tracking(cls, enabled: bool = True) -> None:
        """Enable/disable automatic caller filename tracking in logs."""
        cls._log_caller_filename = enabled

    def set_flush_min_severity(self, severity: Severity) -> None:
        """Change minimum severity written to file."""
        self.flush_min_severity = severity

    def _should_flush_message(self, severity: Severity) -> bool:
        """Check if a message should be written to disk."""
        return self._severity_order[severity] >= self._severity_order[self.flush_min_severity]

    def add(
        self,
        severity: Severity,
        area: Area,
        global_time: int,
        info: str,
        data: Any = None,
    ) -> None:
        """Add message to memory buffer."""

        caller_filename = ""

        if self._log_caller_filename:
            frame = inspect.currentframe()

            if frame is not None:
                caller_frame = frame.f_back

                if caller_frame is not None:
                    caller_filename = inspect.getframeinfo(caller_frame).filename

        extra_data = data if data is not None else ""

        if caller_filename:
            formatted = f"[{severity.value}] ({area.value}) [{caller_filename}] @ {global_time}: {info}, {extra_data}"
        else:
            formatted = f"[{severity.value}] ({area.value}) @ {global_time}: {info}, {extra_data}"

        # Store ALL logs regardless of severity
        self._buffer.append((severity, formatted + "\n"))

        # Auto flush
        if len(self._buffer) >= self.buffer_size:
            self.flush()

    def get(self) -> List[str]:
        """Return all buffered messages."""
        return [message for _, message in self._buffer]

    def flush(self, force: bool = False) -> bool:
        if not (force or len(self._buffer) >= self.buffer_size):
            return False

        messages_to_write = []

        for item in self._buffer:
            if isinstance(item, tuple) and len(item) == 2:
                severity, message = item

                if self._should_flush_message(severity):
                    messages_to_write.append(message)

            else:
                # Backwards compatibility for old string-only buffer entries
                messages_to_write.append(str(item))

        if messages_to_write:
            log_dir = os.path.dirname(self.log_path)

            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            with open(self.log_path, "a", encoding="utf-8") as f:
                if not self._first_flush_done:
                    f.write("--- logger start ---\n")
                    self._first_flush_done = True

                f.writelines(messages_to_write)
                f.flush()

        self._buffer.clear()
        return True
