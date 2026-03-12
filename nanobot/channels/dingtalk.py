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
            
            # Deep Debug: Print full message data and internal attributes
            logger.debug("DEBUG: DingTalk Inbound message.data: {}", json.dumps(message.data, ensure_ascii=False, indent=2))
            
            # [Scheme L: Log Capture] 原原本本记录完整 CallbackMessage 对象
            if self.channel.config.debug_context:
                try:
                    raw_payload = {
                        "topic": getattr(message, "topic", "unknown"),
                        "messageId": getattr(message, "message_id", "unknown"),
                        "extensions": getattr(message, "extensions", {}),
                        "data": message.data
                    }
                    # 使用相对路径并自动创建目录
                    root_dir = Path(__file__).parent.parent.parent
                    debug_dir = root_dir / "workspace/sessions/debug"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_file = debug_dir / "raw_inbound.json"
                    
                    debug_file.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info("Captured raw DingTalk message to {}", debug_file)
                except Exception as log_err:
                    logger.warning("Failed to capture raw message: {}", log_err)

            if self.channel.config.debug_context:
                try:
                    # Log all available attributes of the message object to see if markers are hidden outside .data
                    attrs = {name: str(getattr(message, name)) for name in dir(message) if not name.startswith('_') and not callable(getattr(message, name))}
                    logger.debug("DEBUG: DingTalk CallbackMessage object attributes: {}", attrs)
                except Exception as debug_err:
                    logger.debug("Could not log message attributes: {}", debug_err)


            # Extract text content; fall back to raw dict if SDK object is empty
            content = ""
            if chatbot_msg.text:
                content = chatbot_msg.text.content.strip()
            if not content:
                content = message.data.get("text", {}).get("content", "").strip()
            
            # Extract richText content if available (e.g. from DingTalk Mac client)
            if not content:
                rich_text = message.data.get("content", {}).get("richText")
                if isinstance(rich_text, list):
                    content = "".join([item.get("text", "") for item in rich_text]).strip()
                    if content:
                        logger.info("Extracted content from richText: {}", content)


            metadata = {}
            current_msg_id = message.data.get("msgId")
            if current_msg_id:
                metadata["dingtalk_msg_id"] = current_msg_id

            # Handle quoted messages (Deep Inspection)
            text_field = message.data.get("text", {})
            is_reply = text_field.get("isReplyMsg") or message.data.get("originalMsgId")
            logger.debug("DingTalk message type: {}, is_reply: {}", chatbot_msg.message_type, is_reply)
            
            if is_reply:
                # 1. Gather identifiers
                original_msg_id = message.data.get("originalMsgId")
                original_pq_key = message.data.get("originalProcessQueryKey")
                replied_msg = text_field.get("repliedMsg", {})
                msg_id_to_fetch = original_msg_id or replied_msg.get("msgId")
                
                chatbot_user_id = message.data.get("chatbotUserId", "")
                replied_sender_id = replied_msg.get("senderId", "")
                
                # 2. Scheme H: Determine role and assign specific keys
                is_staff_quote = (replied_sender_id == chatbot_user_id) if (replied_sender_id and chatbot_user_id) else False
                
                if is_staff_quote:
                    # Case: Quoting Assistant (Staff)
                    if original_pq_key:
                        metadata["quote_msg_id"] = original_pq_key
                        logger.info("Identified quote of ASSISTANT with quote_msg_id(pq)={}", original_pq_key)
                    elif msg_id_to_fetch:
                        metadata["quote_msg_id"] = msg_id_to_fetch
                        logger.info("Identified quote of ASSISTANT with quote_msg_id(msgid)={}", msg_id_to_fetch)
                else:
                    # Case: Quoting User (or other human)
                    if msg_id_to_fetch:
                        metadata["quote_msg_id"] = msg_id_to_fetch
                        logger.info("Identified quote of USER with quote_msg_id={}", msg_id_to_fetch)
                
                # 3. Try Local Extraction First (Fastest)
                quote_content = None
                raw = message.data.get("quote", {}).get("content")
                if not raw:
                    raw = replied_msg.get("content")
                if not raw:
                    raw = message.data.get("extensions", {}).get("replyMsgContent")
                
                # Normalize quote content
                if isinstance(raw, dict):
                    quote_content = raw.get("text") or raw.get("content") or raw.get("title") or json.dumps(raw, ensure_ascii=False)
                elif isinstance(raw, str) and raw.strip():
                    quote_content = raw.strip()
                    if quote_content.startswith("{"):
                        try:
                            import json_repair
                            parsed = json_repair.repair_json(quote_content, return_objects=True)
                            if isinstance(parsed, dict):
                                quote_content = parsed.get("text") or parsed.get("title") or parsed.get("content") or quote_content
                        except: pass
                
                # 4. Extract sender meta
                quote_sender = (
                    message.data.get("quote", {}).get("senderNick")
                    or replied_msg.get("senderNick") 
                    or message.data.get("extensions", {}).get("replyMsgSenderNick")
                )
                if quote_sender:
                    metadata["quote_sender"] = quote_sender

                # 5. Context Injection (Scheme K: Keep content clean, metadata only)
                if quote_content:
                    metadata["quote_text"] = quote_content
                    logger.info("Quote content cached in metadata: len={}", len(quote_content))
                else:
                    logger.warning("Local quote extraction failed for msgId={}, no cloud fallback", msg_id_to_fetch)

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

            # 6. Metadata Cleaning (Scheme M)
            # Remove redundant fields completely
            metadata.pop("platform", None)
            
            # Context privilege: Keep ONLY sender info for Group chat
            if conversation_type == "2":
                metadata["sender_name"] = sender_name
                metadata["sender_id"] = sender_id
            
            # Enrichment for immediate context
            if sender_id in self.channel._user_info_cache:
                details = self.channel._user_info_cache[sender_id]
                metadata["sender_title"] = details.get("title", "")
                metadata["sender_dept"] = details.get("dept", "")
                metadata["sender_email"] = details.get("email", "")
                metadata["sender_manager"] = details.get("manager_name", "")
                metadata["sender_org_path"] = details.get("org_path", "")
            
            logger.info(
                "Received DingTalk message from {} ({}) [conv_type={}, conv_id={}]: {}",
                sender_name, sender_id, conversation_type, conversation_id, content,
            )

            # Forward to Nanobot via _on_message (non-blocking).
            task = asyncio.create_task(
                self.channel._on_message(
                    content, sender_id, sender_name,
                    conversation_type=conversation_type,
                    conversation_id=conversation_id,
                    metadata=metadata,
                )
            )
            self.channel._background_tasks.add(task)
            task.add_done_callback(self.channel._background_tasks.discard)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.exception("Error processing DingTalk message: {}", e)
            return AckMessage.STATUS_OK, "Error"


class DingTalkChannel(BaseChannel):
    """
    DingTalk channel using Stream Mode.
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
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._background_tasks: set[asyncio.Task] = set()
        self._recent_replies: dict[str, list[str]] = {}
        self._directory: Any = None
        self._user_info_cache: dict[str, dict[str, Any]] = {}
        self._fetched_user_ids: set[str] = set() # Track IDs fetched in current session to avoid repeat calls

    async def start(self) -> None:
        """Start the DingTalk bot with Stream Mode."""
        try:
            if not DINGTALK_AVAILABLE:
                logger.error("DingTalk Stream SDK not installed.")
                return

            if not self.config.client_id or not self.config.client_secret:
                logger.error("DingTalk client_id and client_secret not configured")
                return

            self._running = True
            self._http = httpx.AsyncClient()

            from nanobot.channels.directory import DingTalkDirectory
            self._directory = DingTalkDirectory(self._http, self._get_access_token)

            credential = Credential(self.config.client_id, self.config.client_secret)
            self._client = DingTalkStreamClient(credential)

            handler = NanobotDingTalkHandler(self)
            self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

            logger.info("DingTalk bot started with Stream Mode")

            while self._running:
                try:
                    await self._client.start()
                except Exception as e:
                    logger.warning("DingTalk stream error: {}", e)
                if self._running:
                    await asyncio.sleep(5)
        except Exception as e:
            logger.exception("Failed to start DingTalk channel: {}", e)

    async def stop(self) -> None:
        """Stop the DingTalk bot."""
        self._running = False
        if self._http:
            await self._http.aclose()
            self._http = None
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()

    async def _get_access_token(self) -> str | None:
        """Get or refresh Access Token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {"appKey": self.config.client_id, "appSecret": self.config.client_secret}

        if not self._http: return None

        try:
            resp = await self._http.post(url, json=data)
            resp.raise_for_status()
            res_data = resp.json()
            self._access_token = res_data.get("accessToken")
            self._token_expiry = time.time() + int(res_data.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as e:
            logger.error("Failed to get DingTalk access token: {}", e)
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

    async def _read_media_bytes(self, media_ref: str) -> tuple[bytes | None, str | None, str | None]:
        if not media_ref: return None, None, None

        if self._is_http_url(media_ref):
            if not self._http: return None, None, None
            try:
                resp = await self._http.get(media_ref, follow_redirects=True)
                if resp.status_code >= 400: return None, None, None
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
                filename = self._guess_filename(media_ref, self._guess_upload_type(media_ref))
                return resp.content, filename, content_type or None
            except Exception as e:
                logger.error("DingTalk media download error ref={} err={}", media_ref, e)
                return None, None, None

        try:
            if media_ref.startswith("file://"):
                local_path = Path(unquote(urlparse(media_ref).path))
            else:
                local_path = Path(os.path.expanduser(media_ref))
            if not local_path.is_file(): return None, None, None
            data = await asyncio.to_thread(local_path.read_bytes)
            return data, local_path.name, mimetypes.guess_type(local_path.name)[0]
        except Exception as e:
            logger.error("DingTalk media read error ref={} err={}", media_ref, e)
            return None, None, None

    async def _upload_media(self, token: str, data: bytes, media_type: str, filename: str, content_type: str | None) -> str | None:
        if not self._http: return None
        url = f"https://oapi.dingtalk.com/media/upload?access_token={token}&type={media_type}"
        mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {"media": (filename, data, mime)}

        try:
            resp = await self._http.post(url, files=files)
            result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code >= 400 or result.get("errcode", 0) != 0: return None
            sub = result.get("result") or {}
            return str(result.get("media_id") or result.get("mediaId") or sub.get("media_id") or sub.get("mediaId"))
        except Exception as e:
            logger.error("DingTalk media upload error type={} err={}", media_type, e)
            return None

    async def _send_private_message(self, token: str, user_id: str, msg_key: str, msg_param: dict[str, Any]) -> str | None:
        if not self._http: return None
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
            if resp.status_code != 200: return None
            result = resp.json()
            # Consistent with Scheme H: Always return processQueryKey for Assistant messages
            return result.get("processQueryKey") or "SUCCESS_NO_ID"
        except Exception as e:
            logger.error("Error sending DingTalk private message: {}", e)
            return None

    async def _send_group_message(self, token: str, open_conversation_id: str, msg_key: str, msg_param: dict[str, Any]) -> str | None:
        if not self._http: return None
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
            if resp.status_code != 200: return None
            result = resp.json()
            # Unified Scheme H: Both return processQueryKey
            return result.get("processQueryKey") or result.get("messageId") or "SUCCESS_NO_ID"
        except Exception as e:
            logger.error("Error sending DingTalk group message: {}", e)
            return None

    async def _send_message(self, token: str, chat_id: str, msg_key: str, msg_param: dict[str, Any], is_group: bool = False) -> str | None:
        if is_group: return await self._send_group_message(token, chat_id, msg_key, msg_param)
        return await self._send_private_message(token, chat_id, msg_key, msg_param)

    def _record_reply(self, chat_id: str, content: str):
        if chat_id not in self._recent_replies: self._recent_replies[chat_id] = []
        self._recent_replies[chat_id].append(content)
        if len(self._recent_replies[chat_id]) > 10: self._recent_replies[chat_id] = self._recent_replies[chat_id][-10:]

    async def _send_markdown_text(self, token: str, chat_id: str, content: str, is_group: bool = False) -> str | None:
        self._record_reply(chat_id, content)
        preview_title = content.replace("#", "").replace("*", "").replace("`", "").replace(">", "").strip().split("\n")[0]
        if len(preview_title) > 30: preview_title = preview_title[:30] + "..."
        return await self._send_message(token, chat_id, "sampleMarkdown", {"text": content, "title": preview_title or "新消息"}, is_group=is_group)

    async def _send_media_ref(self, token: str, chat_id: str, media_ref: str, is_group: bool = False) -> str | None:
        media_ref = (media_ref or "").strip()
        if not media_ref: return "SKIPPED"
        upload_type = self._guess_upload_type(media_ref)
        if upload_type == "image" and self._is_http_url(media_ref):
            msg_id = await self._send_message(token, chat_id, "sampleImageMsg", {"photoURL": media_ref}, is_group=is_group)
            if msg_id: return msg_id

        data, filename, content_type = await self._read_media_bytes(media_ref)
        if not data: return False
        media_id = await self._upload_media(token=token, data=data, media_type=upload_type, filename=filename or "file.bin", content_type=content_type)
        if not media_id: return False

        if upload_type == "image":
            ok = await self._send_message(token, chat_id, "sampleImageMsg", {"photoURL": media_id}, is_group=is_group)
            if ok: return True
        return await self._send_message(token, chat_id, "sampleFile", {"mediaId": media_id, "fileName": filename or "file", "fileType": (filename or "").split(".")[-1] or "bin"}, is_group=is_group)

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through DingTalk."""
        from nanobot.bus.events import MessageReceipt
        token = await self._get_access_token()
        if not token: return

        is_group = msg.metadata.get("conversation_type") == "2"
        remote_id = None
        if msg.content and msg.content.strip():
            remote_id = await self._send_markdown_text(token, msg.chat_id, msg.content.strip(), is_group=is_group)

        for media_ref in msg.media or []:
            media_msg_id = await self._send_media_ref(token, msg.chat_id, media_ref, is_group=is_group)
            remote_id = remote_id or media_msg_id
        
        if remote_id and msg.correlation_id:
            logger.info("Publishing MessageReceipt for correlation_id={}: remote_id={}", msg.correlation_id, remote_id)
            await self.bus.publish_receipt(MessageReceipt(correlation_id=msg.correlation_id, remote_msg_id=remote_id, channel=self.name))

    async def _on_message(self, content: str, sender_id: str, sender_name: str, conversation_type: str | None = None, conversation_id: str | None = None, conversation_title: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        try:
            is_group = conversation_type == "2"
            chat_id = conversation_id if is_group and conversation_id else sender_id
            logger.success("📥 DingTalk inbound [{}]: {} from {} ({})", "group" if is_group else "private", content, sender_name, sender_id)
            await self._handle_message(sender_id=sender_id, chat_id=chat_id, content=str(content), metadata={"sender_name": sender_name, "platform": "dingtalk", "conversation_type": conversation_type or "1", "conversation_title": conversation_title or "", **(metadata or {})}, session_key=None)
        except Exception as e:
            logger.error("Error publishing DingTalk message: {}", e)
