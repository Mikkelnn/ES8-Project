from abc import ABC, abstractmethod


class IModule(ABC):
    """Interface for module implementations."""

    @abstractmethod
    def tick(self, current_global_tick: int) -> tuple[float, int | None]:
        """
        Execute one tick of the module.
        
        Args:
            currentGlobalStep: The current global simulation step.
            
        Returns:
            tuple[ float, int | None]:
            T1 (float): Used power during current tick and ticks until T2.
            T2 (int | None): None if no event scheduled, otherwise the next global tick to evaluate
        """
        ...

    @abstractmethod
    def reset(self, current_global_tick: int) -> None:
        """Reset the module to its initial state. Called when the node dies"""
        ...
