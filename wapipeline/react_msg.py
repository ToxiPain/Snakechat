# wapipeline/react_msg.py — Reacciones con emoji a mensajes
import time
from typing import Any

from protobuf import WAMessage
from .transport import base_jid, is_group, relay_message


def _resolve_target(
    target: Any,
    target_msg_id: str | None,
    target_sender: str | None,
) -> tuple[str | None, str | None]:
    """Extrae (msg_id, sender_jid) desde IncomingMessage, dict, str o campos sueltos."""
    if target is None:
        return target_msg_id, target_sender

    if isinstance(target, str):
        return target, target_sender

    if isinstance(target, dict):
        m_id = target.get("id") or target.get("stanza_id") or target_msg_id
        m_sender = target.get("sender") or target.get("participant") or target_sender
        return m_id, m_sender

    # Objeto estilo IncomingMessage
    m_id = getattr(target, "id", None) or getattr(target, "stanza_id", None) or target_msg_id
    m_sender = getattr(target, "sender", None) or getattr(target, "participant", None) or target_sender
    return m_id, m_sender


async def react_msg(
    ws,
    transport,
    signal_session,
    to_jid: str,
    emoji: str,
    target: Any = None,
    *,
    target_msg_id: str | None = None,
    target_sender: str | None = None,
    debug: bool = False,
) -> str:
    """
    Reacciona a un mensaje con un emoji.

    Ejemplos:
        await react_msg(..., chat_jid, "👍", target=msg)
        await react_msg(..., chat_jid, "👍", target=msg.id, target_sender=msg.sender)
    """
    m_id, m_sender = _resolve_target(target, target_msg_id, target_sender)
    if not m_id:
        raise ValueError("react_msg requiere target (IncomingMessage) o target_msg_id.")

    group = is_group(to_jid)
    base_to = base_jid(to_jid)

    wa_msg = WAMessage()
    wa_msg.react_message.key.remote_jid = base_to
    wa_msg.react_message.key.from_me = False
    wa_msg.react_message.key.id = m_id
    if group and m_sender:
        wa_msg.react_message.key.participant = base_jid(m_sender)
    wa_msg.react_message.text = emoji
    wa_msg.react_message.sender_timestamp_ms = int(time.time() * 1000)

    participants = [m_sender] if m_sender else None

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=wa_msg,
        msg_type="reaction",
        target_participants=participants,
        debug=debug,
    )
    destino = "GRUPO" if group else "CHAT"
    print(f"[>>> REACCIÓN '{emoji}' ({destino})] sobre msg_id={m_id} en {to_jid} (id={msg_id})")
    return msg_id