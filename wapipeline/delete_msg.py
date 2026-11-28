# wapipeline/delete_msg.py — Eliminar mensajes para todos (REVOKE)
from typing import Any

from protobuf import WAMessage
from .handler import base_jid, is_group, relay_message


def _resolve_delete_target(
    target: Any,
    msg_id: str | None,
    sender: str | None,
    from_me: bool | None,
) -> tuple[str | None, str | None, bool]:
    """Extrae (msg_id, sender_jid, from_me) desde str, dict, IncomingMessage o QuotedMessage."""
    if target is None:
        return msg_id, sender, True if from_me is None else from_me

    if isinstance(target, str):
        return target, sender, True if from_me is None else from_me

    if isinstance(target, dict):
        m_id = target.get("id") or target.get("stanza_id") or msg_id
        m_sender = target.get("sender") or target.get("participant") or sender
        m_from_me = target.get("from_me") if from_me is None else from_me
        return m_id, m_sender, False if m_from_me is None else bool(m_from_me)

    # Objeto estilo QuotedMessage o IncomingMessage
    m_id = getattr(target, "id", None) or getattr(target, "stanza_id", None) or msg_id
    m_sender = getattr(target, "sender", None) or getattr(target, "participant", None) or sender
    obj_from_me = getattr(target, "from_me", None)
    if from_me is not None:
        resolved_from_me = from_me
    elif obj_from_me is not None:
        resolved_from_me = bool(obj_from_me)
    else:
        resolved_from_me = False
    return m_id, m_sender, resolved_from_me


async def delete_msg(
    ws,
    transport,
    signal_session,
    to_jid: str,
    target: Any = None,
    *,
    msg_id: str | None = None,
    sender: str | None = None,
    from_me: bool | None = None,
    debug: bool = False,
) -> str:
    """
    Elimina un mensaje para todos (REVOKE).

    Ejemplos:
        # Eliminar un mensaje enviado por el bot:
        sent_id = await client.send_msg(chat_jid, "Me borro en 3 segundos...")
        await client.delete_msg(chat_jid, sent_id)

        # Eliminar el mensaje citado por el usuario (propio o de otro si el bot es admin):
        if umsg.quoted:
            await client.delete_msg(chat_jid, umsg.quoted)
    """
    m_id, m_sender, is_from_me = _resolve_delete_target(target, msg_id, sender, from_me)
    if not m_id:
        raise ValueError("delete_msg requiere target (msg_id, QuotedMessage o IncomingMessage) o msg_id.")

    group = is_group(to_jid)
    base_to = base_jid(to_jid)

    wa_msg = WAMessage()
    wa_msg.protocol_message.type = 0  # REVOKE
    wa_msg.protocol_message.key.remote_jid = base_to
    wa_msg.protocol_message.key.from_me = is_from_me
    wa_msg.protocol_message.key.id = m_id

    if group and not is_from_me and m_sender:
        wa_msg.protocol_message.key.participant = base_jid(m_sender)

    # edit="7" = borrar mensaje propio | edit="8" = admin borra mensaje de otro en grupo
    edit_code = "7" if is_from_me else ("8" if group else "7")
    participants = [m_sender] if m_sender else None

    revoke_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=wa_msg,
        msg_type="text",
        target_participants=participants,
        extra_attrs={"edit": edit_code},
        debug=debug,
    )
    destino = "GRUPO" if group else "CHAT"
    modo = "PROPIO" if is_from_me else "ADMIN"
    print(f"[>>> ELIMINADO ({destino}/{modo})] target_id={m_id} en {to_jid} (revoke_id={revoke_id})")
    return revoke_id