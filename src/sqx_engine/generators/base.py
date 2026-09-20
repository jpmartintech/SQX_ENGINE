from abc import ABC, abstractmethod
class StrategyGenerator(ABC):
    @abstractmethod
    def ask(self): ...
    def tell(self, strategy, result): pass

