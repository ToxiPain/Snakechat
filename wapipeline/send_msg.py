# wapipeline/send_msg.py — Envío de mensajes de texto, reply, menciones de usuario y grupo
# (Consolida: send_msg.py + mention_user.py + mention_group.py como helpers internos)
from typing import Any

from protobuf import WAMessage
from .handler import apply_forward_to_context, base_jid, is_group, relay_message


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS — menciones de usuario
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS — menciones de grupo
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_group_jid(raw_jid: str | None) -> str | None:
    """Convierte un JID o ID de grupo a formato '<id>@g.us' limpio."""
    if not raw_jid or not isinstance(raw_jid, str):
        return None
    cleaned = raw_jid.strip().lstrip("@")
    if not cleaned:
        return None
    if "@" in cleaned:
        resolved = base_jid(cleaned)
        return resolved if resolved.endswith("@g.us") else None
    return f"{cleaned}@g.us"


def _resolve_single_group(
    group: Any,
    default_subject: str | None = None,
) -> tuple[str, str] | None:
    """Extrae (group_jid, group_subject) desde str, tuple, dict o IncomingMessage."""
    if group is None:
        return None

    fallback_subject = (default_subject or "Grupo").strip() or "Grupo"

    if isinstance(group, str):
        g_jid = _normalize_group_jid(group)
        return (g_jid, fallback_subject) if g_jid else None

    if isinstance(group, tuple) and len(group) == 2 and isinstance(group[0], str):
        g_jid = _normalize_group_jid(group[0])
        g_sub = str(group[1]).strip() if group[1] else fallback_subject
        return (g_jid, g_sub or fallback_subject) if g_jid else None

    if isinstance(group, dict):
        raw_jid = (
            group.get("group_jid")
            or group.get("groupJid")
            or group.get("jid")
            or group.get("chat_jid")
        )
        raw_sub = (
            group.get("group_subject")
            or group.get("groupSubject")
            or group.get("subject")
            or group.get("name")
            or fallback_subject
        )
        g_jid = _normalize_group_jid(raw_jid)
        return (g_jid, str(raw_sub).strip() or fallback_subject) if g_jid else None

    # Objeto estilo IncomingMessage o GroupMetadata
    raw_jid = getattr(group, "chat_jid", None) or getattr(group, "jid", None)
    raw_sub = getattr(group, "subject", None) or fallback_subject
    g_jid = _normalize_group_jid(raw_jid)
    return (g_jid, str(raw_sub).strip() or fallback_subject) if g_jid else None


def normalize_group_mentions(
    groups: Any,
    default_subject: str | None = None,
) -> list[tuple[str, str]]:
    """
    Normaliza uno o varios grupos a una lista sin duplicados de (group_jid, group_subject).
    """
    if groups is None:
        return []

    if (
        isinstance(groups, tuple)
        and len(groups) == 2
        and isinstance(groups[0], str)
        and isinstance(groups[1], str)
        and "@g.us" not in groups[1]
    ):
        items = [groups]
    elif isinstance(groups, (list, tuple, set)):
        items = list(groups)
    else:
        items = [groups]

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        resolved = _resolve_single_group(item, default_subject=default_subject)
        if resolved and resolved[0] not in seen:
            seen.add(resolved[0])
            result.append(resolved)
    return result


def tag_group(group: Any) -> str:
    """Devuelve el token '@<id>@g.us' que WhatsApp sustituye por '@<group_subject>'."""
    resolved = _resolve_single_group(group)
    if not resolved:
        return ""
    return f"@{resolved[0]}"


def apply_group_mentions_to_context(
    context_info,
    g_tag: Any,
    default_subject: str | None = None,
) -> list[tuple[str, str]]:
    """Inyecta los GroupMention normalizados en ContextInfo.group_mentions y los devuelve."""
    items = normalize_group_mentions(g_tag, default_subject=default_subject)
    for g_jid, g_subject in items:
        gm = context_info.group_mentions.add()
        gm.group_jid = g_jid
        gm.group_subject = g_subject
    return items


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER INTERNO — resolución de mensaje citado (reply)
# ══════════════════════════════════════════════════════════════════════════════

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

    # Objeto estilo IncomingMessage / QuotedMessage
    q_id = getattr(quoted, "id", None) or getattr(quoted, "stanza_id", None) or quoted_msg_id
    q_sender = getattr(quoted, "sender", None) or getattr(quoted, "participant", None) or quoted_sender
    q_text = getattr(quoted, "text", None) or getattr(quoted, "conversation", None) or quoted_text or ""
    return q_id, q_sender, q_text


# ══════════════════════════════════════════════════════════════════════════════
#  send_msg — texto plano, con reply, tag, g_tag y forward opcionales
# ══════════════════════════════════════════════════════════════════════════════

async def send_msg(
    ws,
    transport,
    signal_session,
    to_jid: str,
    text: str,
    debug: bool = False,
    *,
    reply: Any = None,
    quoted_msg_id: str | None = None,
    quoted_sender: str | None = None,
    quoted_text: str | None = None,
    tag: Any = None,
    g_tag: Any = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
) -> str:
    """
    Envía texto a un chat individual o grupo.

    Parámetros opcionales:
      - reply: IncomingMessage, QuotedMessage, dict o str con el mensaje a citar.
               También puedes pasar quoted_msg_id / quoted_sender / quoted_text sueltos.
      - tag: uno o varios usuarios a mencionar (@usuario).
      - g_tag: uno o varios grupos a mencionar (@Grupo).
      - forward / forwarding_score: etiqueta de reenviado.
    """
    wa_msg = WAMessage()
    target_participants: list[str] = []

    has_reply = bool(reply is not None or quoted_msg_id or quoted_sender or quoted_text)
    has_context = bool(has_reply or tag or g_tag or forward or forwarding_score is not None)

    if has_context:
        wa_msg.extended_text_message.text = text
        ctx = wa_msg.extended_text_message.context_info

        if has_reply:
            q_id, q_sender, q_text = _resolve_quote(reply, quoted_msg_id, quoted_sender, quoted_text)
            if q_id:
                ctx.stanza_id = q_id
            if q_sender:
                ctx.participant = base_jid(q_sender)
                target_participants.append(q_sender)
            if q_text:
                ctx.quoted_message.conversation = q_text

        if tag:
            target_participants.extend(apply_mentions_to_context(ctx, tag))
        if g_tag:
            apply_group_mentions_to_context(ctx, g_tag)
        apply_forward_to_context(ctx, forward=forward, forwarding_score=forwarding_score)
    else:
        wa_msg.conversation = text

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=wa_msg,
        msg_type="text",
        target_participants=target_participants or None,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    if has_reply:
        ref_label = (
            getattr(reply, "id", None)
            or quoted_msg_id
            or "quote"
        )
        print(f"[>>> REPLY ({destino}) a {to_jid} citando {ref_label}] {text!r} (id={msg_id})")
    else:
        print(f"[>>> TEXTO ENVIADO ({destino}) a {to_jid}] {text!r} (id={msg_id})")
    return msg_id


# ══════════════════════════════════════════════════════════════════════════════
#  mention_user — mencionar uno o varios usuarios
# ══════════════════════════════════════════════════════════════════════════════

async def mention_user(
    ws,
    transport,
    signal_session,
    to_jid: str,
    users: Any,
    text: str = "",
    *,
    ghost: bool = False,
    reply: Any = None,
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
    - reply: opcionalmente cita un mensaje al mismo tiempo.
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

    if reply is not None or quoted_msg_id or quoted_sender or quoted_text:
        q_id, q_sender, q_text = _resolve_quote(reply, quoted_msg_id, quoted_sender, quoted_text)
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


# ══════════════════════════════════════════════════════════════════════════════
#  mention_group — mencionar uno o varios grupos
# ══════════════════════════════════════════════════════════════════════════════

async def mention_group(
    ws,
    transport,
    signal_session,
    to_jid: str,
    groups: Any,
    text: str = "",
    *,
    group_subject: str | None = None,
    ghost: bool = False,
    tag: Any = None,
    reply: Any = None,
    quoted_msg_id: str | None = None,
    quoted_sender: str | None = None,
    quoted_text: str | None = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
    debug: bool = False,
) -> str:
    """
    Menciona uno o varios grupos en un chat o grupo.
    """
    resolved_groups = normalize_group_mentions(groups, default_subject=group_subject)
    if not resolved_groups:
        raise ValueError("mention_group requiere al menos un grupo válido (@g.us).")

    final_text = text
    if not ghost:
        missing_tags = [
            f"@{g_jid}"
            for g_jid, _ in resolved_groups
            if f"@{g_jid}" not in final_text
        ]
        if missing_tags:
            prefix = " ".join(missing_tags)
            final_text = f"{prefix} {final_text}".strip() if final_text else prefix

    wa_msg = WAMessage()
    wa_msg.extended_text_message.text = final_text
    ctx = wa_msg.extended_text_message.context_info
    apply_group_mentions_to_context(ctx, resolved_groups)
    apply_forward_to_context(ctx, forward=forward, forwarding_score=forwarding_score)

    target_participants: list[str] = []

    if tag:
        target_participants.extend(apply_mentions_to_context(ctx, tag))

    if reply is not None or quoted_msg_id or quoted_sender or quoted_text:
        q_id, q_sender, q_text = _resolve_quote(reply, quoted_msg_id, quoted_sender, quoted_text)
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
        target_participants=target_participants or None,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    modo = "GROUP-GHOST" if ghost else "GROUP-MENTION"
    resumen = [f"{sub} ({jid})" for jid, sub in resolved_groups]
    print(f"[>>> {modo} ({destino}) a {to_jid} -> {resumen}] {final_text!r} (id={msg_id})")
    return msg_id


# ══════════════════════════════════════════════════════════════════════════════
#  Alias de compatibilidad hacia atrás
# ══════════════════════════════════════════════════════════════════════════════

async def send_text(
    ws,
    transport,
    signal_session,
    to_jid: str,
    text: str,
    debug: bool = False,
    *,
    tag: Any = None,
    g_tag: Any = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
) -> str:
    return await send_msg(
        ws,
        transport,
        signal_session,
        to_jid,
        text,
        debug,
        tag=tag,
        g_tag=g_tag,
        forward=forward,
        forwarding_score=forwarding_score,
    )
