"""Connector interfaces: the only way the agent touches business systems.

The demo ships with simulated connectors (connectors/simulated.py) backed by the
app's own database. To go live for a client, implement these four interfaces
against their real systems (for example SAP or NetSuite for the ERP, Salesforce
or HubSpot for the CRM, Microsoft Graph or Gmail for the mailboxes) and pass them
to the agent. The agent logic does not change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..engine import Snapshot


class ERPConnector(ABC):
    @abstractmethod
    def snapshot(self, today: str) -> Snapshot:
        """Stock, purchase orders, sales orders, customers and carrier lanes in one read."""

    @abstractmethod
    def get_po(self, po: str) -> dict | None: ...

    @abstractmethod
    def list_pos(self) -> list[dict]: ...

    @abstractmethod
    def update_po_deliveries(self, po: str, deliveries: list[dict]) -> None:
        """Write a new arrival schedule, e.g. [{"qty": 280, "date": "2026-11-07"}]."""


class CRMConnector(ABC):
    @abstractmethod
    def get_customer(self, customer_id: str) -> dict | None: ...

    @abstractmethod
    def add_note(self, customer_id: str, text: str) -> None: ...

    @abstractmethod
    def get_quote(self, q: str) -> dict | None: ...

    @abstractmethod
    def update_quote(self, q: str, **fields) -> None: ...


class MailboxConnector(ABC):
    """The shared supply inbox the agent reads."""

    @abstractmethod
    def get_email(self, email_id: int) -> dict | None: ...

    @abstractmethod
    def set_status(self, email_id: int, status: str, run_id: int | None = None) -> None: ...


class OutboxConnector(ABC):
    """Where approved customer messages go."""

    @abstractmethod
    def send(self, *, to: str, customer_id: str, so: str, subject: str, body: str, sent_by: str) -> None: ...
