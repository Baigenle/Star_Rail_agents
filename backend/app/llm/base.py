from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: str
    content: str


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, messages: list[LLMMessage]) -> str:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        raise NotImplementedError
