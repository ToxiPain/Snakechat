# wapipeline/mention_group.py — Menciones a grupos (@Grupo) y helpers globales
from typing import Any

from protobuf import WAMessage
from .transport import apply_forward_to_context, base_jid, is_group, relay_message
from .mention_user import apply_mentions_to_context


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
    quoted: Any = None,
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
        target_participants=target_participants or None,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    modo = "GROUP-GHOST" if ghost else "GROUP-MENTION"
    resumen = [f"{sub} ({jid})" for jid, sub in resolved_groups]
    print(f"[>>> {modo} ({destino}) a {to_jid} -> {resumen}] {final_text!r} (id={msg_id})")
    return msg_id