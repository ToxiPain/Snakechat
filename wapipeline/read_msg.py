# wapipeline/read_msg.py — Marcar mensajes como leídos (doble tick azul)
import time
from typing import Any

from binary import BinaryNode
from .transport import base_jid, is_group, send_node


async def _send_single_read(
    ws,
    transport,
    msg_id: str,
    sender_jid: str,
    chat_jid: str | None = None,
    debug: bool = False,
) -> None:
    to_jid = chat_jid if chat_jid else sender_jid
    group = is_group(to_jid)
    t_now = str(int(time.time()))

    attrs: dict[str, str] = {
        "id": msg_id,
        "to": base_jid(to_jid),
        "type": "read",
        "t": t_now,
    }
    if group:
        attrs["participant"] = base_jid(sender_jid)

    node = BinaryNode(tag="receipt", attrs=attrs)
    await send_node(ws, transport, node, debug)
    destino = "GRUPO" if group else "CHAT"
    print(f"[>>> LEÍDO ({destino})] msg_id={msg_id} sender={sender_jid} t={t_now}")


async def read_msg(
    ws,
    transport,
    target: Any = None,
    sender_jid: str | None = None,
    chat_jid: str | None = None,
    debug: bool = False,
    *,
    msg_id: str | None = None,
) -> None:
    """
    Marca uno o varios mensajes como leídos (doble tick azul).

    Ejemplos:
        await read_msg(..., msg)                # IncomingMessage
        await read_msg(..., [msg1, msg2])       # lista de IncomingMessage o dicts
        await read_msg(..., msg_id="...", sender_jid="...", chat_jid="...")
    """
    if isinstance(target, (list, tuple)):
        for item in target:
            await read_msg(ws, transport, item, sender_jid=sender_jid, chat_jid=chat_jid, debug=debug)
        return

    if target is not None and not isinstance(target, str):
        # IncomingMessage o dict
        if isinstance(target, dict):
            resolved_id = target.get("id") or msg_id
            resolved_sender = target.get("sender") or sender_jid
            resolved_chat = target.get("chat_jid") if target.get("chat_jid") != resolved_sender else chat_jid
        else:
            resolved_id = getattr(target, "id", None) or msg_id
            resolved_sender = getattr(target, "sender", None) or sender_jid
            is_grp = getattr(target, "is_group", False)
            raw_chat = getattr(target, "chat_jid", None)
            resolved_chat = (raw_chat if is_grp else None) if chat_jid is None else chat_jid
    else:
        resolved_id = msg_id or target
        resolved_sender = sender_jid
        resolved_chat = chat_jid

    if not resolved_id or not resolved_sender:
        raise ValueError("read_msg requiere msg_id/IncomingMessage y sender_jid.")

    await _send_single_read(
        ws=ws,
        transport=transport,
        msg_id=resolved_id,
        sender_jid=resolved_sender,
        chat_jid=resolved_chat,
        debug=debug,
    )