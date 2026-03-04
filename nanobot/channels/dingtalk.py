"""DingTalk/DingDing channel implementation using Stream Mode."""

import asyncio
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from loguru import logger
import httpx

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import DingTalkConfig

try:
    from dingtalk_stream import (
        DingTalkStreamClient,
        Credential,
        CallbackHandler,
        CallbackMessage,
        AckMessage,
    )
    from dingtalk_stream.chatbot import ChatbotMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    # Fallback so class definitions don't crash at module level
    CallbackHandler = object  # type: ignore[assignment,misc]
    CallbackMessage = None  # type: ignore[assignment,misc]
    AckMessage = None  # type: ignore[assignment,misc]
    ChatbotMessage = None  # type: ignore[assignment,misc]


class NanobotDingTalkHandler(CallbackHandler):
    """
    Standard DingTalk Stream SDK Callback Handler.
    Parses incoming messages and forwards them to the Nanobot channel.
    """

    def __init__(self, channel: "DingTalkChannel"):
        super().__init__()
        self.channel = channel

    async def process(self, message: CallbackMessage):
        """Process incoming stream message."""
        try:
            # Parse using SDK's ChatbotMessage for robust handling
            chatbot_msg = ChatbotMessage.from_dict(message.data)

            # Extract text content; fall back to raw dict if SDK object is empty
            content = ""
            if chatbot_msg.text:
                content = chatbot_msg.text.content.strip()
            if not content:
                content = message.data.get("text", {}).get("content", "").strip()

            # Handle quoted messages (Deep Inspection & Remote Fetch)
            text_field = message.data.get("text", {})
            is_reply = text_field.get("isReplyMsg") or message.data.get("originalMsgId")
            
            if is_reply:
                # 1. Gather identifiers
                original_msg_id = message.data.get("originalMsgId")
                replied_msg = text_field.get("repliedMsg", {})
                msg_id_to_fetch = original_msg_id or replied_msg.get("msgId")
                chatbot_user_id = message.data.get("chatbotUserId", "")
                replied_sender_id = replied_msg.get("senderId", "")
                replied_msg_type = replied_msg.get("msgType", "")
                
                # 2. Determine if the quoted message is from Staff (the bot itself)
                is_staff_quote = (replied_sender_id == chatbot_user_id) if chatbot_user_id else False
                
                # 3. Try Local Extraction First (Fastest)
                quote_content = None
                # Try top-level quote field
                raw = message.data.get("quote", {}).get("content")
                if not raw:
                    raw = replied_msg.get("content")
                if not raw:
                    raw = message.data.get("extensions", {}).get("replyMsgContent")
                
                # Normalize: content can be a dict like {"text": "内容"} or a plain string
                if isinstance(raw, dict):
                    quote_content = raw.get("text") or raw.get("content") or raw.get("title") or json.dumps(raw, ensure_ascii=False)
                elif isinstance(raw, str) and raw.strip():
                    quote_content = raw.strip()
                    # Also try to parse JSON strings
                    if quote_content.startswith("{"):
                        try:
                            import json_repair
                            parsed = json_repair.repair_json(quote_content, return_objects=True)
                            if isinstance(parsed, dict):
                                quote_content = parsed.get("text") or parsed.get("title") or parsed.get("content") or quote_content
                        except: pass
                
                # Determine sender label
                quote_sender = (
                    message.data.get("quote", {}).get("senderNick")
                    or replied_msg.get("senderNick")
                    or message.data.get("extensions", {}).get("replyMsgSenderNick")
                )
                
                # 4. Fallback for Staff quotes (interactiveCard) with no content
                if not quote_content and is_staff_quote:
                    # Try per-chat recent message cache (most reliable for Staff's own replies)
                    sender_id = (message.data.get("senderStaffId")
                                 or message.data.get("senderId", ""))
                    recent = self.channel._recent_replies.get(sender_id, [])
                    if recent:
                        quote_content = recent[-1]  # Most recent reply to this user
                        quote_sender = "Staff助理"
                        logger.info("Recovered Staff quote from per-chat cache for user {}", sender_id)
                
                # 5. Remote Fetch Fallback (API)
                if not quote_content and msg_id_to_fetch:
                    logger.info("Quote content missing, fetching remotely: {}", msg_id_to_fetch)
                    remote_details = await self.channel._get_message_details(msg_id_to_fetch)
                    if remote_details:
                        rc = remote_details.get("content")
                        if isinstance(rc, dict):
                            quote_content = rc.get("text") or rc.get("content") or json.dumps(rc, ensure_ascii=False)
                        elif isinstance(rc, str):
                            quote_content = rc
                        quote_sender = remote_details.get("senderNick") or remote_details.get("senderId")
                
                # 6. Context Injection
                if quote_content:
                    sender_label = quote_sender if quote_sender else ("Staff助理" if is_staff_quote else "先前消息")
                    content = f"[引用自 {sender_label}: {quote_content}]\n------------------\n{content}"
                    logger.info("Quote context injected: sender={}", sender_label)
                else:
                    # We know it's a reply but can't get content — indicate this
                    label = "Staff助理的先前回复" if is_staff_quote else "先前消息"
                    content = f"[针对{label}的回复]\n------------------\n{content}"

            if not content:
                logger.warning(
                    "Received empty or unsupported message type: {}",
                    chatbot_msg.message_type,
                )
                return AckMessage.STATUS_OK, "OK"

            sender_id = chatbot_msg.sender_staff_id or chatbot_msg.sender_id
            sender_name = chatbot_msg.sender_nick or "Unknown"
            conversation_type = chatbot_msg.conversation_type  # "1"=private, "2"=group
            conversation_id = chatbot_msg.conversation_id  # openConversationId for group
            conversation_title = getattr(chatbot_msg, "conversation_title", "")

            logger.info(
                "Received DingTalk message from {} ({}) [conv_type={}, conv_id={}]: {}",
                sender_name, sender_id, conversation_type, conversation_id, content,
            )

            # Forward to Nanobot via _on_message (non-blocking).
            # Store reference to prevent GC before task completes.
            task = asyncio.create_task(
                self.channel._on_message(
                    content, sender_id, sender_name,
                    conversation_type=conversation_type,
                    conversation_id=conversation_id,
                    conversation_title=conversation_title,
                )
            )
            self.channel._background_tasks.add(task)
            task.add_done_callback(self.channel._background_tasks.discard)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.error("Error processing DingTalk message: {}", e)
            # Return OK to avoid retry loop from DingTalk server
            return AckMessage.STATUS_OK, "Error"


class DingTalkChannel(BaseChannel):
    """
    DingTalk channel using Stream Mode.

    Uses WebSocket to receive events via `dingtalk-stream` SDK.
    Uses direct HTTP API to send messages (SDK is mainly for receiving).

    Supports both private (1:1) chat and group chat.
    Group messages are replied to within the group via orgGroupSend API.
    """

    name = "dingtalk"
    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    _AUDIO_EXTS = {".amr", ".mp3", ".wav", ".ogg", ".m4a", ".aac"}
    _VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def __init__(self, config: DingTalkConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DingTalkConfig = config
        self._client: Any = None
        self._http: httpx.AsyncClient | None = None

        # Access Token management for sending messages
        self._access_token: str | None = None
        self._token_expiry: float = 0

        # Hold references to background tasks to prevent GC
        self._background_tasks: set[asyncio.Task] = set()

        # Per-chat recent reply cache for quote recovery
        # Maps chat_id -> list of recent reply texts (last 10 per user)
        self._recent_replies: dict[str, list[str]] = {}

        # Organization directory API (initialized in start())
        self._directory: Any = None

    async def start(self) -> None:
        """Start the DingTalk bot with Stream Mode."""
        try:
            if not DINGTALK_AVAILABLE:
                logger.error(
                    "DingTalk Stream SDK not installed. Run: pip install dingtalk-stream"
                )
                return

            if not self.config.client_id or not self.config.client_secret:
                logger.error("DingTalk client_id and client_secret not configured")
                return

            self._running = True
            self._http = httpx.AsyncClient()

            # Initialize organization directory API
            from nanobot.channels.directory import DingTalkDirectory
            self._directory = DingTalkDirectory(self._http, self._get_access_token)

            logger.info(
                "Initializing DingTalk Stream Client with Client ID: {}...",
                self.config.client_id,
            )
            credential = Credential(self.config.client_id, self.config.client_secret)
            self._client = DingTalkStreamClient(credential)

            # Register standard handler
            handler = NanobotDingTalkHandler(self)
            self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

            logger.info("DingTalk bot started with Stream Mode")

            # Reconnect loop: restart stream if SDK exits or crashes
            while self._running:
                try:
                    await self._client.start()
                except Exception as e:
                    logger.warning("DingTalk stream error: {}", e)
                if self._running:
                    logger.info("Reconnecting DingTalk stream in 5 seconds...")
                    await asyncio.sleep(5)

        except Exception as e:
            logger.exception("Failed to start DingTalk channel: {}", e)

    async def stop(self) -> None:
        """Stop the DingTalk bot."""
        self._running = False
        # Close the shared HTTP client
        if self._http:
            await self._http.aclose()
            self._http = None
        # Cancel outstanding background tasks
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()

    async def _get_access_token(self) -> str | None:
        """Get or refresh Access Token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {
            "appKey": self.config.client_id,
            "appSecret": self.config.client_secret,
        }

        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot refresh token")
            return None

        try:
            resp = await self._http.post(url, json=data)
            resp.raise_for_status()
            res_data = resp.json()
            self._access_token = res_data.get("accessToken")
            # Expire 60s early to be safe
            self._token_expiry = time.time() + int(res_data.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as e:
            logger.error("Failed to get DingTalk access token: {}", e)
            return None

    async def _get_message_details(self, msg_id: str) -> dict[str, Any] | None:
        """Fetch message details from DingTalk OpenAPI via msgId."""
        token = await self._get_access_token()
        if not token or not self._http:
            return None

        url = "https://api.dingtalk.com/v1.0/robot/messageDetails/get"
        headers = {"x-acs-dingtalk-access-token": token}
        payload = {"msgId": msg_id}

        try:
            resp = await self._http.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.debug("DingTalk messageDetail failed status={} msgId={}", resp.status_code, msg_id)
                return None
            return resp.json()
        except Exception as e:
            logger.error("Error fetching DingTalk message details for {}: {}", msg_id, e)
            return None

    @staticmethod
    def _is_http_url(value: str) -> bool:
        return urlparse(value).scheme in ("http", "https")

    def _guess_upload_type(self, media_ref: str) -> str:
        ext = Path(urlparse(media_ref).path).suffix.lower()
        if ext in self._IMAGE_EXTS: return "image"
        if ext in self._AUDIO_EXTS: return "voice"
        if ext in self._VIDEO_EXTS: return "video"
        return "file"

    def _guess_filename(self, media_ref: str, upload_type: str) -> str:
        name = os.path.basename(urlparse(media_ref).path)
        return name or {"image": "image.jpg", "voice": "audio.amr", "video": "video.mp4"}.get(upload_type, "file.bin")

    async def _read_media_bytes(
        self,
        media_ref: str,
    ) -> tuple[bytes | None, str | None, str | None]:
        if not media_ref:
            return None, None, None

        if self._is_http_url(media_ref):
            if not self._http:
                return None, None, None
            try:
                resp = await self._http.get(media_ref, follow_redirects=True)
                if resp.status_code >= 400:
                    logger.warning(
                        "DingTalk media download failed status={} ref={}",
                        resp.status_code,
                        media_ref,
                    )
                    return None, None, None
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
                filename = self._guess_filename(media_ref, self._guess_upload_type(media_ref))
                return resp.content, filename, content_type or None
            except Exception as e:
                logger.error("DingTalk media download error ref={} err={}", media_ref, e)
                return None, None, None

        try:
            if media_ref.startswith("file://"):
                parsed = urlparse(media_ref)
                local_path = Path(unquote(parsed.path))
            else:
                local_path = Path(os.path.expanduser(media_ref))
            if not local_path.is_file():
                logger.warning("DingTalk media file not found: {}", local_path)
                return None, None, None
            data = await asyncio.to_thread(local_path.read_bytes)
            content_type = mimetypes.guess_type(local_path.name)[0]
            return data, local_path.name, content_type
        except Exception as e:
            logger.error("DingTalk media read error ref={} err={}", media_ref, e)
            return None, None, None

    async def _upload_media(
        self,
        token: str,
        data: bytes,
        media_type: str,
        filename: str,
        content_type: str | None,
    ) -> str | None:
        if not self._http:
            return None
        url = f"https://oapi.dingtalk.com/media/upload?access_token={token}&type={media_type}"
        mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {"media": (filename, data, mime)}

        try:
            resp = await self._http.post(url, files=files)
            text = resp.text
            result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code >= 400:
                logger.error("DingTalk media upload failed status={} type={} body={}", resp.status_code, media_type, text[:500])
                return None
            errcode = result.get("errcode", 0)
            if errcode != 0:
                logger.error("DingTalk media upload api error type={} errcode={} body={}", media_type, errcode, text[:500])
                return None
            sub = result.get("result") or {}
            media_id = result.get("media_id") or result.get("mediaId") or sub.get("media_id") or sub.get("mediaId")
            if not media_id:
                logger.error("DingTalk media upload missing media_id body={}", text[:500])
                return None
            return str(media_id)
        except Exception as e:
            logger.error("DingTalk media upload error type={} err={}", media_type, e)
            return None

    async def _send_private_message(
        self,
        token: str,
        user_id: str,
        msg_key: str,
        msg_param: dict[str, Any],
    ) -> bool:
        """Send a message to a user via private (1:1) chat."""
        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot send")
            return False

        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}
        payload = {
            "robotCode": self.config.client_id,
            "userIds": [user_id],
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
        }

        try:
            resp = await self._http.post(url, json=payload, headers=headers)
            body = resp.text
            if resp.status_code != 200:
                logger.error("DingTalk private send failed msgKey={} status={} body={}", msg_key, resp.status_code, body[:500])
                return False
            try: result = resp.json()
            except Exception: result = {}

            errcode = result.get("errcode")
            if errcode not in (None, 0):
                logger.error("DingTalk private send api error msgKey={} errcode={} body={}", msg_key, errcode, body[:500])
                return False
            logger.debug("DingTalk private message sent to {} with msgKey={}", user_id, msg_key)
            return True
        except Exception as e:
            logger.error("Error sending DingTalk private message msgKey={} err={}", msg_key, e)
            return False

    async def _send_group_message(
        self,
        token: str,
        open_conversation_id: str,
        msg_key: str,
        msg_param: dict[str, Any],
    ) -> bool:
        """Send a message to a group chat via orgGroupSend API."""
        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot send")
            return False

        url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
        headers = {"x-acs-dingtalk-access-token": token}
        payload = {
            "robotCode": self.config.client_id,
            "openConversationId": open_conversation_id,
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
        }

        try:
            resp = await self._http.post(url, json=payload, headers=headers)
            body = resp.text
            if resp.status_code != 200:
                logger.error("DingTalk group send failed msgKey={} status={} body={}", msg_key, resp.status_code, body[:500])
                return False
            try: result = resp.json()
            except Exception: result = {}

            errcode = result.get("errcode")
            if errcode not in (None, 0):
                logger.error("DingTalk group send api error msgKey={} errcode={} body={}", msg_key, errcode, body[:500])
                return False
            logger.debug("DingTalk group message sent to conv={} with msgKey={}", open_conversation_id, msg_key)
            return True
        except Exception as e:
            logger.error("Error sending DingTalk group message msgKey={} err={}", msg_key, e)
            return False

    async def _send_message(
        self,
        token: str,
        chat_id: str,
        msg_key: str,
        msg_param: dict[str, Any],
        is_group: bool = False,
    ) -> bool:
        """Route message to group or private send method."""
        if is_group:
            return await self._send_group_message(token, chat_id, msg_key, msg_param)
        return await self._send_private_message(token, chat_id, msg_key, msg_param)

    def _record_reply(self, chat_id: str, content: str):
        """Record sent message content per chat for quote recovery."""
        if chat_id not in self._recent_replies:
            self._recent_replies[chat_id] = []
        self._recent_replies[chat_id].append(content)
        # Keep only last 10 messages per chat
        if len(self._recent_replies[chat_id]) > 10:
            self._recent_replies[chat_id] = self._recent_replies[chat_id][-10:]

    async def _send_markdown_text(self, token: str, chat_id: str, content: str, is_group: bool = False) -> bool:
        # Record the reply for quote recovery BEFORE sending
        self._record_reply(chat_id, content)
        # 生成预览标题：去除 Markdown 符号并截断
        preview_title = content.replace("#", "").replace("*", "").replace("`", "").replace(">", "").strip()
        preview_title = preview_title.split("\n")[0]  # 取第一行
        if len(preview_title) > 30:
            preview_title = preview_title[:30] + "..."
        if not preview_title:
            preview_title = "新消息"

        return await self._send_message(
            token,
            chat_id,
            "sampleMarkdown",
            {"text": content, "title": preview_title},
            is_group=is_group,
        )

    async def _send_media_ref(self, token: str, chat_id: str, media_ref: str, is_group: bool = False) -> bool:
        media_ref = (media_ref or "").strip()
        if not media_ref:
            return True

        upload_type = self._guess_upload_type(media_ref)
        if upload_type == "image" and self._is_http_url(media_ref):
            ok = await self._send_message(
                token,
                chat_id,
                "sampleImageMsg",
                {"photoURL": media_ref},
                is_group=is_group,
            )
            if ok:
                return True
            logger.warning("DingTalk image url send failed, trying upload fallback: {}", media_ref)

        data, filename, content_type = await self._read_media_bytes(media_ref)
        if not data:
            logger.error("DingTalk media read failed: {}", media_ref)
            return False

        filename = filename or self._guess_filename(media_ref, upload_type)
        file_type = Path(filename).suffix.lower().lstrip(".")
        if not file_type:
            guessed = mimetypes.guess_extension(content_type or "")
            file_type = (guessed or ".bin").lstrip(".")
        if file_type == "jpeg":
            file_type = "jpg"

        media_id = await self._upload_media(
            token=token,
            data=data,
            media_type=upload_type,
            filename=filename,
            content_type=content_type,
        )
        if not media_id:
            return False

        if upload_type == "image":
            # Verified in production: sampleImageMsg accepts media_id in photoURL.
            ok = await self._send_message(
                token,
                chat_id,
                "sampleImageMsg",
                {"photoURL": media_id},
                is_group=is_group,
            )
            if ok:
                return True
            logger.warning("DingTalk image media_id send failed, falling back to file: {}", media_ref)

        return await self._send_message(
            token,
            chat_id,
            "sampleFile",
            {"mediaId": media_id, "fileName": filename, "fileType": file_type},
            is_group=is_group,
        )

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through DingTalk."""
        token = await self._get_access_token()
        if not token:
            return

        is_group = msg.metadata.get("conversation_type") == "2"

        if msg.content and msg.content.strip():
            await self._send_markdown_text(token, msg.chat_id, msg.content.strip(), is_group=is_group)

        for media_ref in msg.media or []:
            ok = await self._send_media_ref(token, msg.chat_id, media_ref, is_group=is_group)
            if ok:
                continue
            logger.error("DingTalk media send failed for {}", media_ref)
            # Send visible fallback so failures are observable by the user.
            filename = self._guess_filename(media_ref, self._guess_upload_type(media_ref))
            await self._send_markdown_text(
                token,
                msg.chat_id,
                f"[Attachment send failed: {filename}]",
                is_group=is_group,
            )

    async def _on_message(
        self,
        content: str,
        sender_id: str,
        sender_name: str,
        conversation_type: str | None = None,
        conversation_id: str | None = None,
        conversation_title: str | None = None,
    ) -> None:
        """Handle incoming message (called by NanobotDingTalkHandler).

        Delegates to BaseChannel._handle_message() which enforces allow_from
        permission checks before publishing to the bus.
        """
        try:
            is_group = conversation_type == "2"
            # For group chat, chat_id is the openConversationId;
            # For private chat, chat_id is the sender_id.
            chat_id = conversation_id if is_group and conversation_id else sender_id
            
            # Allow group chats to share context instead of isolating per sender
            session_key = None

            logger.success(
                "📥 DingTalk inbound [{}]: {} from {} ({})",
                "group" if is_group else "private", content, sender_name, sender_id,
            )
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=str(content),
                metadata={
                    "sender_name": sender_name,
                    "platform": "dingtalk",
                    "conversation_type": conversation_type or "1",
                    "conversation_title": conversation_title or "",
                },
                session_key=session_key,
            )
        except Exception as e:
            logger.error("Error publishing DingTalk message: {}", e)
