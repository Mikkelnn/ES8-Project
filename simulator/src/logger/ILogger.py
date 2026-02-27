from abc import ABC, abstractmethod
from typing import Any
from custom_types import Area, LogMessage, Severity

class ILogger(ABC):
    """Abstract base class describing the logger API.

    Concrete implementations must provide :py:meth:`add` and
    :py:meth:`flush`.  ``pending`` is provided as an abstract property.
    """

    @abstractmethod
    def add(self, severity: Severity, area: Area, global_time: int, msg: str, data: Any = None) -> None:
        """Append a log message to the logger's buffer."""

    @abstractmethod
    def flush(self, force: bool = False) -> bool:
        """Flush buffered messages.

        ``force`` forces a flush regardless of buffer length.  Returns ``True``
        when messages were written.
        """