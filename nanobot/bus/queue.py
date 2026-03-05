"""Async message queue for decoupled channel-agent communication."""

import asyncio

from nanobot.bus.events import InboundMessage, OutboundMessage, MessageReceipt


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    Receipts flow back from channels to the agent to confirm delivery IDs.
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self.receipt: asyncio.Queue[MessageReceipt] = asyncio.Queue()
        
        # Mapping correlation_id -> asyncio.Future for synchronous waiting
        self._receipt_futures: dict[str, asyncio.Future] = {}

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    async def publish_receipt(self, receipt: MessageReceipt) -> None:
        """Publish a delivery confirmation from a channel."""
        # 1. Provide to async queue for legacy background loops (if any)
        await self.receipt.put(receipt)
        
        # 2. Complete synchronous waiters (Scheme D)
        if receipt.correlation_id in self._receipt_futures:
            future = self._receipt_futures.pop(receipt.correlation_id)
            if not future.done():
                future.set_result(receipt.remote_msg_id)

    async def wait_for_receipt(self, correlation_id: str, timeout: float = 3.0) -> str | None:
        """
        Wait synchronously (non-blocking) for a specific message receipt.
        Returns the remote_msg_id if received within timeout, else None.
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._receipt_futures[correlation_id] = future
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # Clean up on timeout
            self._receipt_futures.pop(correlation_id, None)
            return None
        except Exception:
            self._receipt_futures.pop(correlation_id, None)
            raise

    async def consume_receipt(self) -> MessageReceipt:
        """Consume the next message receipt (blocks until available)."""
        return await self.receipt.get()

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()
    
    @property
    def receipt_size(self) -> int:
        """Number of pending receipts."""
        return self.receipt.qsize()
