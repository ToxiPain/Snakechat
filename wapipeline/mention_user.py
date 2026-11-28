# wapipeline/mention_user.py — Menciones a usuarios (@usuario) y helpers globales
from typing import Any

from protobuf import WAMessage
from .transport import apply_forward_to_context, base_jid, is_group, relay_message


def _resolve_single_jid(user: Any) -> str | None:
    """Convierte un IncomingMessage, dict, número o JID a su JID base limpio."""
    if user is None:
        return None

    if isinstance(user, str):
        raw = user.strip().lstrip("@")
        if not raw:
            return None
        if "@" in raw:
            return base_jid(raw)
        digits = "".join(ch for ch in raw if ch.isdigit())
        return f"{digits}@s.whatsapp.net" if digits else None

    if isinstance(user, dict):
        raw = user.get("sender") or user.get("jid") or user.get("participant") or user.get("number")
        return _resolve_single_jid(raw)

    # Objeto estilo IncomingMessage
    raw = getattr(user, "sender_base", None) or getattr(user, "sender", None) or getattr(user, "jid", None)
    return _resolve_single_jid(raw)


def normalize_mention_jids(users: Any) -> list[str]:
    """Normaliza uno o varios usuarios a una lista sin duplicados de JIDs base."""
    if users is None:
        return []
    items = users if isinstance(users, (list, tuple, set)) else [users]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        jid = _resolve_single_jid(item)
        if jid and jid not in seen:
            seen.add(jid)
            result.append(jid)
    return result


def tag_user(user: Any) -> str:
    """Devuelve el tag visible '@<id>' que coincide con el JID en mentioned_jid."""
    jid = _resolve_single_jid(user)
    if not jid:
        return ""
    return f"@{jid.split('@', 1)[0]}"


def apply_mentions_to_context(context_info, mentions: Any) -> list[str]:
    """Inyecta los JIDs normalizados en ContextInfo.mentioned_jid y los devuelve."""
    jids = normalize_mention_jids(mentions)
    if jids:
        context_info.mentioned_jid.extend(jids)
    return jids


async def mention_user(
    ws,
    transport,
    signal_session,
    to_jid: str,
    users: Any,
    text: str = "",
    *,
    ghost: bool = False,
    quoted: Any = None,
    quoted_msg_id: str | None = None,
    quoted_sender: str | None = None,
    quoted_text: str | None = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
    debug: bool = False,
) -> str:
    """
    Menciona a uno o varios usuarios en un chat o grupo.

    - ghost=False (por defecto): si el texto no contiene los '@<id>', los antepone automáticamente.
    - ghost=True: mención oculta/fantasma (notifica al usuario sin mostrar el '@' en el texto).
    - quoted: opcionalmente cita un mensaje al mismo tiempo.
    - forward / forwarding_score: etiqueta de reenviado opcional.
    """
    mentioned_jids = normalize_mention_jids(users)
    if not mentioned_jids:
        raise ValueError("mention_user requiere al menos un usuario válido para mencionar.")

    final_text = text
    if not ghost:
        missing_tags = [
            f"@{jid.split('@', 1)[0]}"
            for jid in mentioned_jids
            if f"@{jid.split('@', 1)[0]}" not in final_text
        ]
        if missing_tags:
            prefix = " ".join(missing_tags)
            final_text = f"{prefix} {final_text}".strip() if final_text else prefix

    wa_msg = WAMessage()
    wa_msg.extended_text_message.text = final_text
    ctx = wa_msg.extended_text_message.context_info
    ctx.mentioned_jid.extend(mentioned_jids)
    apply_forward_to_context(ctx, forward=forward, forwarding_score=forwarding_score)

    target_participants = list(mentioned_jids)

    if quoted is not None or quoted_msg_id or quoted_sender or quoted_text:
        from .reply_msg import _resolve_quote

        q_id, q_sender, q_text = _resolve_quote(quoted, quoted_msg_id, quoted_sender, quoted_text)
        if q_id:
            ctx.stanza_id = q_id
        if q_sender:
            ctx.participant = base_jid(q_sender)
            target_participants.append(q_sender)
        if q_text:
            ctx.quoted_message.conversation = q_text

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=wa_msg,
        msg_type="text",
        target_participants=target_participants,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    modo = "GHOST" if ghost else "MENTION"
    print(f"[>>> {modo} ({destino}) a {to_jid} -> {mentioned_jids}] {final_text!r} (id={msg_id})")
    return msg_id