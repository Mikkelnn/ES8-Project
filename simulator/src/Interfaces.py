from abc import ABC, abstractmethod


class IDevice(ABC):
	"""Interface for device implementations."""

	@abstractmethod
	def tick(self, current_global_tick: int) -> int | None:
		"""
		Execute one tick of the device.

		Args:
			currentGlobalStep: The current global simulation step.

		Returns:
			int | None: None if no event scheduled, otherwise the next global tick to evaluate
		"""
		...


class ILength(ABC):
	@property
	def length(self) -> int:
		"""Returns the length of the data in bytes."""
		raise NotImplementedError()
