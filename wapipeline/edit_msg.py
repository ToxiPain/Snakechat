# wapipeline/edit_msg.py — Editar mensajes enviados por el bot (MESSAGE_EDIT)
import time
from typing import Any

from protobuf import WAMessage
from .transport import base_jid, is_group, relay_message
from .mention_user import apply_mentions_to_context
from .mention_group import apply_group_mentions_to_context


def _varint(n: int) -> bytes:
    if n < 0:
        n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _field_varint(field_num: int, val: int) -> bytes:
    return _varint((field_num << 3) | 0) + _varint(val)


def _field_bytes(field_num: int, val: bytes) -> bytes:
    return _varint((field_num << 3) | 2) + _varint(len(val)) + val


def _field_str(field_num: int, val: str) -> bytes:
    return _field_bytes(field_num, val.encode("utf-8"))


def _resolve_edit_msg_id(target: Any, msg_id: str | None) -> str | None:
    if target is None:
        return msg_id
    if isinstance(target, str):
        return target
    if isinstance(target, dict):
        return target.get("id") or target.get("stanza_id") or msg_id
    return getattr(target, "id", None) or getattr(target, "stanza_id", None) or msg_id


def _build_edit_proto(
    remote_jid: str,
    target_msg_id: str,
    edited_wa_msg: WAMessage,
    timestamp_ms: int,
) -> bytes:
    """
    Construye WAMessage con ProtocolMessage (type=14 MESSAGE_EDIT):
      - field 1: key (MessageKey: remote_jid, from_me=True, id)
      - field 2: type = 14 (MESSAGE_EDIT)
      - field 14: edited_message (WAMessage)
      - field 15: timestamp_ms (int64)
    """
    key_bytes = (
        _field_str(1, remote_jid)
        + _field_varint(2, 1)  # from_me = True
        + _field_str(3, target_msg_id)
    )
    proto_msg_bytes = (
        _field_bytes(1, key_bytes)
        + _field_varint(2, 14)  # MESSAGE_EDIT
        + _field_bytes(14, edited_wa_msg.SerializeToString())
        + _field_varint(15, timestamp_ms)
    )
    # WAMessage field 12 = protocol_message
    return _field_bytes(12, proto_msg_bytes)


async def edit_msg(
    ws,
    transport,
    signal_session,
    to_jid: str,
    target: Any,
    new_text: str,
    *,
    msg_id: str | None = None,
    tag: Any = None,
    g_tag: Any = None,
    debug: bool = False,
) -> str:
    """
    Edita un mensaje enviado previamente por el bot.

    Ejemplos:
        sent_id = await client.send_msg(chat_jid, "Texto original")
        await client.edit_msg(chat_jid, sent_id, "Texto editado ✏️")
    """
    target_id = _resolve_edit_msg_id(target, msg_id)
    if not target_id:
        raise ValueError("edit_msg requiere el msg_id del mensaje a editar.")

    base_to = base_jid(to_jid)
    edited_wa = WAMessage()
    target_participants: list[str] | None = None

    if tag or g_tag:
        edited_wa.extended_text_message.text = new_text
        ctx = edited_wa.extended_text_message.context_info
        if tag:
            target_participants = apply_mentions_to_context(ctx, tag)
        if g_tag:
            apply_group_mentions_to_context(ctx, g_tag)
    else:
        edited_wa.conversation = new_text

    raw_proto = _build_edit_proto(
        remote_jid=base_to,
        target_msg_id=target_id,
        edited_wa_msg=edited_wa,
        timestamp_ms=int(time.time() * 1000),
    )

    edit_stanza_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=raw_proto,
        msg_type="text",
        target_participants=target_participants,
        extra_attrs={"edit": "1"},
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    print(f"[>>> EDITADO ({destino})] target_id={target_id} en {to_jid} -> {new_text!r} (id={edit_stanza_id})")
    return edit_stanza_id