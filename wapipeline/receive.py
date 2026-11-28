# Procesamiento de mensajes entrantes: extracción de texto, menciones, quoted, forward, ACKs y retry
import struct
import time

from protobuf import WAMessage
from binary import BinaryNode
from crypto.keys import xeddsa_sign


def _base_jid(jid: str | None) -> str | None:
    """Devuelve el JID base (sin device) a partir de un JID completo."""
    if not jid or "@" not in jid:
        return jid
    user_part, server = jid.split("@", 1)
    base_user = user_part.split(":")[0]
    return f"{base_user}@{server}"


def _extract_text_from_wa_msg(msg: WAMessage) -> str | None:
    if msg.HasField("conversation"):
        return msg.conversation
    if msg.HasField("extended_text_message") and msg.extended_text_message.HasField("text"):
        return msg.extended_text_message.text
    return None


def extract_text(raw_proto: bytes) -> str | None:
    msg = WAMessage()
    msg.ParseFromString(raw_proto)
    return _extract_text_from_wa_msg(msg)


def extract_mentions(raw_proto: bytes) -> list[str]:
    msg = WAMessage()
    msg.ParseFromString(raw_proto)
    if (
        msg.HasField("extended_text_message")
        and msg.extended_text_message.HasField("context_info")
    ):
        return list(msg.extended_text_message.context_info.mentioned_jid)
    return []


def extract_group_mentions(raw_proto: bytes) -> list[dict[str, str]]:
    msg = WAMessage()
    msg.ParseFromString(raw_proto)
    if (
        msg.HasField("extended_text_message")
        and msg.extended_text_message.HasField("context_info")
    ):
        return [
            {
                "group_jid": gm.group_jid,
                "group_subject": gm.group_subject,
            }
            for gm in msg.extended_text_message.context_info.group_mentions
            if gm.group_jid
        ]
    return []


def extract_forward_info(raw_proto: bytes) -> tuple[bool, int]:
    """Devuelve (is_forwarded, forwarding_score) desde ContextInfo."""
    msg = WAMessage()
    msg.ParseFromString(raw_proto)
    if (
        msg.HasField("extended_text_message")
        and msg.extended_text_message.HasField("context_info")
    ):
        ctx = msg.extended_text_message.context_info
        return bool(ctx.is_forwarded), int(ctx.forwarding_score)
    return False, 0


def extract_quoted(
    raw_proto: bytes,
    chat_jid: str,
    my_jids: list[str | None] | None = None,
):
    """Extrae el mensaje citado (reply) desde ContextInfo si existe."""
    from .handler import QuotedMessage  # deferred to avoid circular import at load time

    msg = WAMessage()
    msg.ParseFromString(raw_proto)
    if not (
        msg.HasField("extended_text_message")
        and msg.extended_text_message.HasField("context_info")
    ):
        return None

    ctx = msg.extended_text_message.context_info
    if not ctx.stanza_id:
        return None

    q_sender = ctx.participant or chat_jid
    q_text = _extract_text_from_wa_msg(ctx.quoted_message) if ctx.HasField("quoted_message") else None

    my_base_set = {_base_jid(j) for j in (my_jids or []) if j}
    q_sender_base = _base_jid(q_sender)
    is_from_me = bool(q_sender_base and q_sender_base in my_base_set)

    return QuotedMessage(
        id=ctx.stanza_id,
        sender=q_sender,
        chat_jid=chat_jid,
        text=q_text,
        from_me=is_from_me,
    )


def print_incoming_message(node: BinaryNode, sender: str, text: str):
    push_name = node.attrs.get("notify", "")
    msg_id = node.attrs.get("id", "")
    label = f"{push_name} ({sender})" if push_name else sender
    print(f"[<<< MENSAJE de {label}] {text!r}  (id={msg_id})")


def build_ack(node: BinaryNode) -> BinaryNode:
    attrs = {
        "id": node.attrs.get("id", ""),
        "to": node.attrs.get("from", "s.whatsapp.net"),
        "class": node.tag,
    }
    if node.tag != "message" and "type" in node.attrs:
        attrs["type"] = node.attrs["type"]
    if "participant" in node.attrs:
        attrs["participant"] = node.attrs["participant"]
    return BinaryNode(tag="ack", attrs=attrs)


def build_retry_receipt(node: BinaryNode, pairing, prekeys) -> BinaryNode:
    msg_id = node.attrs.get("id", "")
    ts = node.attrs.get("t", str(int(time.time())))
    attrs = {"id": msg_id, "to": node.attrs.get("from", ""), "type": "retry", "t": ts}
    if "participant" in node.attrs:
        attrs["participant"] = node.attrs["participant"]

    key_id, key_pub = prekeys.generate_batch(1)[0]
    skey_sig = xeddsa_sign(pairing.ident_priv_bytes, b"\x05" + pairing.skey_pub_bytes)

    keys_children = [
        BinaryNode(tag="type", content=b"\x05"),
        BinaryNode(tag="identity", content=pairing.ident_pub_bytes),
        BinaryNode(tag="key", content=[
            BinaryNode(tag="id", content=struct.pack(">I", key_id)[1:]),
            BinaryNode(tag="value", content=key_pub),
        ]),
        BinaryNode(tag="skey", content=[
            BinaryNode(tag="id", content=struct.pack(">I", 1)[1:]),
            BinaryNode(tag="value", content=pairing.skey_pub_bytes),
            BinaryNode(tag="signature", content=skey_sig),
        ]),
    ]
    if pairing.account_bytes:
        keys_children.append(BinaryNode(tag="device-identity", content=pairing.account_bytes))

    return BinaryNode(
        tag="receipt",
        attrs=attrs,
        content=[
            BinaryNode(tag="retry", attrs={"v": "1", "count": "2", "id": msg_id, "t": ts}),
            BinaryNode(tag="registration", content=struct.pack(">I", pairing.reg_id)),
            BinaryNode(tag="keys", content=keys_children),
        ],
    )
