# wapipeline/reply_msg.py — Envío de mensajes citando (reply con quote, tag, g_tag y forward opcionales)
from typing import Any

from protobuf import WAMessage
from .transport import apply_forward_to_context, base_jid, is_group, relay_message
from .mention_user import apply_mentions_to_context
from .mention_group import apply_group_mentions_to_context


def _resolve_quote(
    quoted: Any,
    quoted_msg_id: str | None,
    quoted_sender: str | None,
    quoted_text: str | None,
) -> tuple[str | None, str | None, str]:
    """Extrae (stanza_id, participant, quoted_text) desde IncomingMessage, dict, str o campos sueltos."""
    if quoted is None:
        return quoted_msg_id, quoted_sender, quoted_text or ""

    if isinstance(quoted, str):
        return quoted_msg_id, quoted_sender, quoted

    if isinstance(quoted, dict):
        q_id = quoted.get("id") or quoted.get("stanza_id") or quoted_msg_id
        q_sender = quoted.get("sender") or quoted.get("participant") or quoted_sender
        q_text = quoted.get("text") or quoted.get("conversation") or quoted_text or ""
        return q_id, q_sender, q_text

    # Objeto estilo IncomingMessage
    q_id = getattr(quoted, "id", None) or getattr(quoted, "stanza_id", None) or quoted_msg_id
    q_sender = getattr(quoted, "sender", None) or getattr(quoted, "participant", None) or quoted_sender
    q_text = getattr(quoted, "text", None) or getattr(quoted, "conversation", None) or quoted_text or ""
    return q_id, q_sender, q_text


async def reply_msg(
    ws,
    transport,
    signal_session,
    to_jid: str,
    text: str,
    quoted: Any = None,
    *,
    quoted_msg_id: str | None = None,
    quoted_sender: str | None = None,
    quoted_text: str | None = None,
    tag: Any = None,
    g_tag: Any = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
    debug: bool = False,
) -> str:
    """
    Envía un mensaje citando (reply) a otro, con soporte opcional de tag, g_tag y forward.
    """
    q_id, q_sender, q_text = _resolve_quote(quoted, quoted_msg_id, quoted_sender, quoted_text)

    wa_msg = WAMessage()
    wa_msg.extended_text_message.text = text
    ctx = wa_msg.extended_text_message.context_info

    if q_id:
        ctx.stanza_id = q_id
    if q_sender:
        ctx.participant = base_jid(q_sender)
    if q_text:
        ctx.quoted_message.conversation = q_text

    participants: list[str] = []
    if q_sender:
        participants.append(q_sender)
    if tag:
        participants.extend(apply_mentions_to_context(ctx, tag))
    if g_tag:
        apply_group_mentions_to_context(ctx, g_tag)
    apply_forward_to_context(ctx, forward=forward, forwarding_score=forwarding_score)

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=wa_msg,
        msg_type="text",
        target_participants=participants or None,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    ref_label = q_id or "quote"
    print(f"[>>> REPLY ({destino}) a {to_jid} citando {ref_label}] {text!r} (id={msg_id})")
    return msg_id