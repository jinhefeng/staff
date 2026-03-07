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
        self.tickets_dir = ensure_dir(workspace / "tickets")
        self.db_file = self.tickets_dir / "active_tickets.json"
        self.archive_file = self.tickets_dir / "archived_tickets.jsonl"
        self.tickets: Dict[str, Dict[str, Any]] = self._load()

    def _cleanup_stale_tickets(self) -> None:
        """Archived resolved tickets and tickets older than 7 days to prevent bloat."""
        now = datetime.now()
        to_archive = []
        timeout_delta = timedelta(days=7)

        for tk, meta in list(self.tickets.items()):
            # Archive if it's explicitly marked as 'resolved' 
            # (Note: resolve_ticket now pops and archives directly, but we check just in case)
            if meta.get("resolved", False):
                to_archive.append(tk)
                continue
                
            # Archive if older than 7 days
            created_at = datetime.fromisoformat(meta["created_at"])
            if now - created_at > timeout_delta:
                meta["archive_reason"] = "timeout (7 days)"
                to_archive.append(tk)

        if not to_archive:
            return

        try:
            with open(self.archive_file, "a", encoding="utf-8") as f:
                for tk in to_archive:
                    meta = self.tickets.pop(tk)
                    meta["archived_at"] = now.isoformat()
                    f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            logger.info("Archived {} stale tickets to {}.", len(to_archive), self.archive_file)
            self._save()
        except Exception:
            logger.exception("Failed to clean up stale tickets.")

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.db_file.exists():
            try:
                content = self.db_file.read_text(encoding="utf-8")
                loaded = json.loads(content)
                return loaded
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

    def create_ticket(self, guest_id: str, channel: str, chat_id: str, content: str, guest_name: str = "") -> str:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        self.tickets[ticket_id] = {
            "ticket_id": ticket_id,
            "guest_id": guest_id,
            "guest_name": guest_name or guest_id,
            "guest_channel": channel,
            "guest_chat_id": chat_id,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "pacified": False,
        }
        self._save()
        logger.info("Created async ticket {} for guest {} ({})", ticket_id, guest_name or guest_id, guest_id)
        
        # Trigger an asynchronous clean up to prevent memory bloat over time
        self._cleanup_stale_tickets()
        
        return ticket_id

    def resolve_ticket(self, ticket_id: str) -> Dict[str, Any] | None:
        """Removes the ticket from active tracking, archives it and returns it."""
        ticket = self.tickets.pop(ticket_id, None)
        if ticket:
            ticket["resolved"] = True
            ticket["resolved_at"] = datetime.now().isoformat()
            
            # Write to archive directly upon resolution
            try:
                with open(self.archive_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ticket, ensure_ascii=False) + "\n")
            except Exception:
                logger.exception("Failed to write resolved ticket {} to archive.", ticket_id)
                
            self._save()
            logger.info("Resolved and archived async ticket {}", ticket_id)
        return ticket

    def approve_ticket(self, ticket_id: str) -> Dict[str, Any] | None:
        """Mark a deferred task ticket as 'approved' by Master.
        
        Unlike resolve_ticket, this does NOT archive the ticket.
        It stays in active_tickets.json with status='approved' so HeartbeatService
        can pick it up for execution.
        """
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket["status"] = "approved"
        ticket["approved_at"] = datetime.now().isoformat()
        ticket["heartbeat_retries"] = 0
        self._save()
        logger.info("Master approved deferred ticket {}", ticket_id)
        return ticket

    def get_approved_deferred_tickets(self) -> List[Dict[str, Any]]:
        """Returns all deferred task tickets that have been approved but not yet resolved."""
        result = []
        for tk, meta in self.tickets.items():
            if meta.get("status") == "approved" and not meta.get("resolved", False):
                result.append(meta)
        return result

    def increment_heartbeat_retries(self, ticket_id: str) -> int:
        """Increment the heartbeat retry counter for a ticket. Returns new count."""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return -1
        count = ticket.get("heartbeat_retries", 0) + 1
        ticket["heartbeat_retries"] = count
        self._save()
        return count

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

    def get_summary(self, guest_id: str | None = None) -> str:
        """Returns a concise summary of active tickets.
        If guest_id is provided, only returns tickets related to that guest.
        """
        filtered = []
        for tk, meta in self.tickets.items():
            if guest_id and meta.get("guest_id") != guest_id:
                continue
            # Keep summary concise
            content = meta.get("content", "")
            if len(content) > 60:
                content = content[:57] + "..."
            created = meta.get("created_at", "")[:16].replace("T", " ")
            filtered.append(f"- [{tk}] {content} (Created: {created})")

        if not filtered:
            return "No active tickets."
        return "\n".join(filtered)
