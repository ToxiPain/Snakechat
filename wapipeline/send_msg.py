# wapipeline/send_msg.py — Envío de mensajes de texto plano (con tag, g_tag y forward opcionales)
from typing import Any

from protobuf import WAMessage
from .transport import apply_forward_to_context, is_group, relay_message
from .mention_user import apply_mentions_to_context
from .mention_group import apply_group_mentions_to_context


async def send_msg(
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
    """Envía texto a un chat individual o grupo, con soporte opcional de tag, g_tag y forward."""
    wa_msg = WAMessage()
    target_participants: list[str] | None = None

    has_context = bool(tag or g_tag or forward or forwarding_score is not None)
    if has_context:
        wa_msg.extended_text_message.text = text
        ctx = wa_msg.extended_text_message.context_info
        if tag:
            target_participants = apply_mentions_to_context(ctx, tag)
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
        target_participants=target_participants,
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    print(f"[>>> TEXTO ENVIADO ({destino}) a {to_jid}] {text!r} (id={msg_id})")
    return msg_id


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