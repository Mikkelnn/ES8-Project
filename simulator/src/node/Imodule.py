from typing import Protocol


class IModule(Protocol):
    """Interface for module implementations."""

    def tick(self, currentGlobalTick: int) -> tuple[float, int | None]:
        """
        Execute one tick of the module.
        
        Args:
            currentGlobalStep: The current global simulation step.
            
        Returns:
            tuple[ float, int | None]:
            T1 (float): Used power for tick.
            T2 (int | None): None if no event scheduled, otherwise the next global tick to evaluate
        """
        ...

    def reset(self, current_global_tick: int) -> None:
        """Reset the module to its initial state."""
        ...
