from typing import Protocol


class IModule(Protocol):
    """Interface for module implementations."""

    def tick(self, currentGlobalTick: int) -> float:
        """
        Execute one tick of the module.
        
        Args:
            currentGlobalStep: The current global simulation step.
            
        Returns:
            float: Used power for tick.
        """
        ...

    def reset(self) -> None:
        """Reset the module to its initial state."""
        ...
