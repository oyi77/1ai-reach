import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

import pandas as pd

try:
    import requests as _req
    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger
from oneai_reach.application.outreach.reply_classifier import ReplyClassifier

logger = get_logger(__name__)


class ReplyTrackerService:

    def __init__(self, config: Settings):
        self.config = config
        self.gmail_account = config.gmail.account
        self.gmail_keyring_password = config.gmail.keyring_password
        self.waha_url = config.waha.url
        self.waha_direct_url = config.waha.direct_url
        self.waha_api_key = config.waha.api_key
        self.waha_direct_api_key = config.waha.direct_api_key
        self.waha_session = config.waha.session
        self._classifier = None

    def check_replies(
        self,
        df: pd.DataFrame,
        update_lead_fn,
        get_wa_numbers_fn,
        db_connect_fn,
        parse_display_name_fn,
        is_empty_fn,
        normalize_phone_fn,
        cs_handle_fn=None,
        warmcall_process_fn=None,
        get_or_create_conversation_fn=None,
    ) -> int:
        for col in ("status", "replied_at"):
            if col not in df.columns:
                df[col] = None
            df[col] = df[col].astype(object)

        contacted = df[
            df["status"].isin(["contacted", "followed_up"])
            & df["email"].notna()
            & ~df["email"].apply(is_empty_fn)
        ]

        if contacted.empty:
            logger.info("No contacted leads to check for replies")
            return 0

        logger.info(f"Checking {len(contacted)} contacted leads for replies")

        messages = self._gog_search(f"in:inbox -from:{self.gmail_account}")
        if not messages:
            messages = self._gog_search("in:inbox")

        if not messages:
            logger.warning("No messages found in inbox")
            self._check_replies_himalaya(df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn)
            return 0

        inbox_replies: Dict[str, str] = {}
        for m in messages:
            sender = self._extract_sender_email(m)
            if sender:
                body = m.get("body", "") or m.get("snippet", "") or m.get("text", "") or ""
                inbox_replies[sender] = str(body).strip()[:2000]

        updated = 0
        for index, row in contacted.iterrows():
            lead_email = str(row.get("email") or "").strip().lower()
            if not lead_email:
                continue
            if lead_email in inbox_replies:
                name = parse_display_name_fn(row.get("displayName"))
                reply_text = inbox_replies[lead_email]
                category, priority = self._classify_and_log_reply(name, lead_email, reply_text, "EMAIL")
                df.at[index, "status"] = "replied"
                df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
                lead_id = str(row.get("id") or row.name or "")
                if lead_id and reply_text:
                    ai_category, ai_suggested_reply = self.classifier.get_ai_triage(reply_text)

                    try:
                        update_lead_fn(
                            lead_id,
                            reply_text=reply_text,
                            ai_triage_category=ai_category,
                            ai_suggested_reply=ai_suggested_reply
                        )
                        self._forward_reply_with_triage("EMAIL", name, lead_email, reply_text, ai_category, ai_suggested_reply)
                    except Exception as e:
                        logger.error(f"Failed to store reply text for {name}: {e}")
                updated += 1

        self._check_replies_waha(
            df, contacted, update_lead_fn, get_wa_numbers_fn, db_connect_fn,
            parse_display_name_fn, is_empty_fn, normalize_phone_fn,
            cs_handle_fn, warmcall_process_fn, get_or_create_conversation_fn,
        )

        logger.info(f"Reply check complete. {updated} new replies detected")
        return updated


    def _forward_reply_with_triage(self, channel: str, lead_name: str, contact_info: str, reply_text: str, ai_category: str, ai_suggested_reply: str):
        try:
            from oneai_reach.infrastructure.messaging.email_sender import EmailSender
            sender = EmailSender(self.config)
            target = "grahainsanmandiri@gmail.com"
            subject = f"[{channel} REPLY] New reply from {lead_name} ({contact_info})"
            
            body = f"New {channel.lower()} reply from {lead_name} ({contact_info}):\n\n"
            body += f"AI Triage Category: {ai_category}\n"
            body += f"AI Suggested Reply: {ai_suggested_reply}\n\n"
            body += f"{reply_text}\n\n---\n"
            body += "Automated Forwarding by 1ai-reach"
            
            success = sender.send(target, subject, body)
            if success:
                logger.info(f"Forwarded {channel} reply to {target}")
            else:
                logger.warning(f"Failed to forward {channel} reply to {target}")
        except Exception as e:
            logger.error(f"Error forwarding reply: {e}")

    def _gog_search(self, query: str) -> List[dict]:
        env = {
            **os.environ,
            "GOG_KEYRING_PASSWORD": self.gmail_keyring_password,
            "GOG_ACCOUNT": self.gmail_account,
        }
        cmd = ["/home/linuxbrew/.linuxbrew/bin/gog", "gmail", "search", "-j"]
        if query:
            cmd.append(query)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("threads", data.get("messages", [data]))
        except Exception as e:
            logger.error(f"gog search failed: {e}")
        return []

    def _extract_sender_email(self, thread: dict) -> str:
        val = thread.get("from", "")
        if not val:
            return ""
        if "<" in val and ">" in val:
            return val.split("<")[1].rstrip(">").strip().lower()
        return val.strip().lower()

    def _waha_targets(self) -> List[Tuple[str, str, Dict[str, str]]]:
        targets: List[Tuple[str, str, Dict[str, str]]] = []
        seen: set[Tuple[str, str]] = set()
        for name, base_url, api_key in [
            ("WAHA", self.waha_url, self.waha_api_key),
            ("WAHA_DIRECT", self.waha_direct_url, self.waha_direct_api_key),
        ]:
            url = str(base_url or "").rstrip("/")
            key = str(api_key or "")
            if not url or (url, key) in seen:
                continue
            seen.add((url, key))
            targets.append((name, url, {"X-Api-Key": key}))
        return targets

    def _waha_sessions(self, base_url: str, headers: Dict[str, str], get_wa_numbers_fn) -> List[dict]:
        api_session_names: List[str] = []
        if _HTTP_OK:
            try:
                r = _req.get(f"{base_url}/api/sessions", params={"all": "true"}, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        for item in data:
                            name = str(item.get("name") or "").strip()
                            status = str(item.get("status") or "").upper()
                            if name and status == "WORKING":
                                api_session_names.append(name)
            except Exception:
                pass

        if self.waha_session and self.waha_session not in api_session_names:
            api_session_names.insert(0, self.waha_session)

        try:
            wa_rows = get_wa_numbers_fn()
        except Exception:
            wa_rows = []

        wa_by_session: Dict[str, dict] = {}
        for row in wa_rows:
            sn = row.get("session_name", "")
            if sn:
                wa_by_session[sn] = row

        if wa_by_session:
            all_session_names = list(dict.fromkeys(api_session_names + list(wa_by_session.keys())))
            result: List[dict] = []
            for sn in all_session_names:
                db_row = wa_by_session.get(sn)
                mode = db_row["mode"] if db_row and db_row.get("mode") else "cold"
                wa_id = db_row["id"] if db_row else None
                result.append({"session_name": sn, "mode": mode, "wa_number_id": wa_id})
            return result

        return [{"session_name": sn, "mode": "cold", "wa_number_id": None} for sn in api_session_names]

    def _is_waha_msg_processed(self, waha_message_id: str, db_connect_fn) -> bool:
        if not waha_message_id:
            return False
        conn = db_connect_fn()
        try:
            row = conn.execute("SELECT id FROM conversation_messages WHERE waha_message_id = ?", (waha_message_id,)).fetchone()
            return row is not None
        except Exception:
            return False
        finally:
            conn.close()

    def _check_replies_waha(self, df, contacted, update_lead_fn, get_wa_numbers_fn, db_connect_fn, parse_display_name_fn, is_empty_fn, normalize_phone_fn, cs_handle_fn, warmcall_process_fn, get_or_create_conversation_fn):
        if not _HTTP_OK:
            return
        last_error = ""
        for target_name, base_url, headers in self._waha_targets():
            sessions = self._waha_sessions(base_url, headers, get_wa_numbers_fn)
            for sess_info in sessions:
                session_name = sess_info["session_name"]
                mode = sess_info["mode"]
                wa_number_id = sess_info["wa_number_id"]
                try:
                    r = _req.get(f"{base_url}/api/chats", params={"session": session_name, "limit": 100}, headers=headers, timeout=10)
                    if r.status_code != 200:
                        last_error = f"{target_name} ({session_name}) chats error {r.status_code}"
                        continue
                    raw = r.json()
                    chats = raw if isinstance(raw, list) else raw.get("chats", [])
                    for chat in chats:
                        chat_id = str(chat.get("id", {}).get("user", "") or chat.get("id", ""))
                        if not chat_id:
                            continue
                        last_msg = chat.get("lastMessage") or {}
                        waha_msg_id = str(last_msg.get("id", "") or chat.get("messageId", "") or "").strip()
                        if self._is_waha_msg_processed(waha_msg_id, db_connect_fn):
                            continue
                        body = str(last_msg.get("body", "") or chat.get("last_message", "") or chat.get("body", "") or "").strip()[:2000]
                        if not body:
                            continue
                        contact_phone = chat_id
                        digits = self._phone_digits(chat_id, normalize_phone_fn)
                        self._route_waha_message(mode, wa_number_id, session_name, contact_phone, digits, body, waha_msg_id, target_name, df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn, cs_handle_fn, warmcall_process_fn, get_or_create_conversation_fn)
                    return
                except Exception as e:
                    last_error = f"{target_name} ({session_name}) reply check error: {e}"
        if last_error:
            logger.error(last_error)

    def _phone_digits(self, phone: str, normalize_phone_fn) -> str:
        p = normalize_phone_fn(phone)
        return p.lstrip("+") if p else ""

    def _route_waha_message(self, mode, wa_number_id, session_name, contact_phone, digits, body, waha_msg_id, target_name, df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn, cs_handle_fn, warmcall_process_fn, get_or_create_conversation_fn):
        if mode == "cs" and cs_handle_fn is not None:
            effective_wa_id = wa_number_id or session_name
            try:
                ai_category, ai_suggested_reply = self.classifier.get_ai_triage(body)
                cs_handle_fn(
                    effective_wa_id,
                    contact_phone,
                    body,
                    session_name,
                    ai_triage_category=ai_category,
                    ai_suggested_reply=ai_suggested_reply
                )
                logger.info(f"🤖 CS handled: {contact_phone} [via {target_name}/{session_name}] with category {ai_category}")
            except Exception as e:
                logger.error(f"cs_engine error for {contact_phone}: {e}")
            return
        if mode == "warmcall" and warmcall_process_fn is not None:
            try:
                effective_wa_id = wa_number_id or session_name
                conv_id = get_or_create_conversation_fn(effective_wa_id, contact_phone, "warmcall")
                warmcall_process_fn(conv_id, body)
                logger.info(f"🔥 Warmcall handled: {contact_phone} [via {target_name}/{session_name}]")
            except Exception as e:
                logger.error(f"warmcall_engine error for {contact_phone}: {e}")
            return
        self._handle_cold_reply(digits, body, target_name, session_name, df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn)

    def _handle_cold_reply(self, digits, body, target_name, session_name, df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn):
        for index, row in contacted.iterrows():
            phone = str(row.get("internationalPhoneNumber") if pd.notna(row.get("internationalPhoneNumber")) else row.get("phone") if pd.notna(row.get("phone")) else "").strip()
            if not phone or is_empty_fn(phone):
                continue
            lead_digits = self._phone_digits(phone, lambda p: p)
            if lead_digits != digits:
                continue
            if str(df.at[index, "status"]) == "replied":
                continue
            name = parse_display_name_fn(row.get("displayName"))
            category, priority = self._classify_and_log_reply(name, phone, body, "WHATSAPP")
            df.at[index, "status"] = "replied"
            df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
            lead_id = str(row.get("id") or row.name or "")
            if lead_id and body:
                try:
                    update_lead_fn(lead_id, reply_text=body)
                    self._forward_reply("WHATSAPP", name, phone, body)
                except Exception as e:
                    logger.error(f"Failed to store WA reply text for {name}: {e}")
            return

    def _check_replies_himalaya(self, df, contacted, update_lead_fn, parse_display_name_fn, is_empty_fn):
        try:
            result = subprocess.run(["/home/linuxbrew/.linuxbrew/bin/himalaya", "envelope", "list", "--output", "json"], capture_output=True, text=True, timeout=30)
            if result.returncode != 0 or not result.stdout.strip():
                logger.error("Himalaya fallback also failed")
                return
            messages = json.loads(result.stdout)
            inbox_replies: Dict[str, str] = {}
            for m in messages:
                sender = m.get("from", {})
                if isinstance(sender, dict):
                    addr = sender.get("addr", "").lower()
                elif isinstance(sender, str):
                    addr = sender.lower()
                else:
                    addr = ""
                if "@" in addr:
                    body = str(m.get("body", "") or m.get("text", "") or m.get("subject", "") or "").strip()[:2000]
                    inbox_replies[addr] = body
            for index, row in contacted.iterrows():
                lead_email = str(row.get("email") or "").strip().lower()
                if lead_email in inbox_replies:
                    name = parse_display_name_fn(row.get("displayName"))
                    reply_text = inbox_replies[lead_email]
                    category, priority = self._classify_and_log_reply(name, lead_email, reply_text, "EMAIL")
                    df.at[index, "status"] = "replied"
                    df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
                    lead_id = str(row.get("id") or row.name or "")
                    if lead_id and reply_text:
                        try:
                            update_lead_fn(lead_id, reply_text=reply_text)
                            self._forward_reply("EMAIL", name, lead_email, reply_text)
                        except Exception as e:
                            logger.error(f"Failed to store reply text for {name}: {e}")
        except Exception as e:
            logger.error(f"Himalaya fallback error: {e}")

    @property
    def classifier(self) -> ReplyClassifier:
        if self._classifier is None:
            self._classifier = ReplyClassifier()
        return self._classifier

    def _classify_and_log_reply(self, name: str, contact: str, reply_text: str, channel: str) -> Tuple[str, int]:
        """Classify reply and log with sentiment emoji.
        
        Returns (category, priority_score).
        """
        category, confidence = self.classifier.classify(reply_text)
        priority = self.classifier.get_priority_score(category, confidence)
        
        emojis = {
            "positive": "🟢",
            "inquiry": "🔵",
            "neutral": "🟡",
            "negative": "🔴",
        }
        emoji = emojis.get(category, "⚪")
        
        logger.info(f"{emoji} {channel} REPLY from {name} ({contact}) - {category.upper()} (confidence: {confidence}%, priority: {priority})")
        
        return (category, priority)
