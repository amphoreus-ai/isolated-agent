"""Generic registry for pluggable components."""
from typing import TypeVar, Generic

T = TypeVar("T")


class Registry(Generic[T]):
    """A registry for named components (agents, backends)."""

    def __init__(self, kind: str = "component"):
        self._items: dict[str, type[T]] = {}
        self._kind = kind

    def register(self, name: str, cls: type[T]) -> None:
        if name in self._items:
            raise ValueError(f"{self._kind} '{name}' is already registered")
        self._items[name] = cls

    def get(self, name: str) -> type[T]:
        if name not in self._items:
            available = ", ".join(sorted(self._items.keys())) or "(none)"
            raise KeyError(f"Unknown {self._kind} '{name}'. Available: {available}")
        return self._items[name]

    def list(self) -> list[str]:
        return sorted(self._items.keys())
