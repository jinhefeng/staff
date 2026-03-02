"""Ticket manager for handling asynchronous auto-pacifier wait loops."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger
import uuid

from nanobot.utils.helpers import ensure_dir

class TicketManager:
    """Manages asynchronous tickets escalated to Master."""

    def __init__(self, workspace: Path):
        self.tickets_dir = ensure_dir(workspace / "memory" / "tickets")
        self.db_file = self.tickets_dir / "active_tickets.json"
        self.tickets: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.db_file.exists():
            try:
                content = self.db_file.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception:
                logger.exception("Failed to load tickets db.")
                return {}
        return {}

    def _save(self) -> None:
        try:
            content = json.dumps(self.tickets, ensure_ascii=False, indent=2)
            self.db_file.write_text(content, encoding="utf-8")
        except Exception:
            logger.exception("Failed to save tickets db.")

    def create_ticket(self, guest_id: str, channel: str, chat_id: str, content: str) -> str:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        self.tickets[ticket_id] = {
            "ticket_id": ticket_id,
            "guest_id": guest_id,
            "guest_channel": channel,
            "guest_chat_id": chat_id,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "pacified": False,
        }
        self._save()
        logger.info("Created async ticket {} for guest {}", ticket_id, guest_id)
        return ticket_id

    def resolve_ticket(self, ticket_id: str) -> Dict[str, Any] | None:
        """Removes the ticket from active tracking and returns it."""
        ticket = self.tickets.pop(ticket_id, None)
        if ticket:
            self._save()
            logger.info("Resolved async ticket {}", ticket_id)
        return ticket

    def get_stalled_tickets(self, timeout_minutes: int = 30) -> List[Dict[str, Any]]:
        """Returns tickets that are older than timeout_minutes and haven't been pacified yet."""
        stalled = []
        now = datetime.now()
        for tk, metadata in self.tickets.items():
            if not metadata.get("pacified", False):
                created_at = datetime.fromisoformat(metadata["created_at"])
                if now - created_at > timedelta(minutes=timeout_minutes):
                    stalled.append(metadata)
        return stalled

    def mark_pacified(self, ticket_id: str) -> None:
        """Marks a ticket as having received an auto-pacifier message."""
        if ticket_id in self.tickets:
            self.tickets[ticket_id]["pacified"] = True
            self.tickets[ticket_id]["pacified_at"] = datetime.now().isoformat()
            self._save()
            logger.info("Marked ticket {} as pacified", ticket_id)

    def is_waiting(self, guest_id: str) -> bool:
        """Checks if a guest has an active un-resolved ticket."""
        for tk, meta in self.tickets.items():
            if meta.get("guest_id") == guest_id:
                return True
        return False
