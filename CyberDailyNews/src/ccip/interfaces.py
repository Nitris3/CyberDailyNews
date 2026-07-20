"""Ports implemented by collectors, processors, and delivery adapters."""

from __future__ import annotations

from collections.abc import Sequence
from email.message import EmailMessage
from typing import Protocol

from ccip.domain import CollectedItem, IntelligenceItem


class Collector(Protocol):
    @property
    def name(self) -> str: ...

    def collect(self) -> Sequence[CollectedItem]: ...


class Processor(Protocol):
    def process(self, item: CollectedItem) -> IntelligenceItem | None: ...


class EmailDelivery(Protocol):
    def deliver(self, message: EmailMessage) -> None: ...

