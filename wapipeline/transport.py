# Capa de transporte: envío de BinaryNodes y motor común de cifrado/envío (relay_message)
import os
import struct

from binary import BinaryNode, encode_binary_node
from protobuf import WAMessage


def is_group(jid: str) -> bool:
    return "@g.us" in jid


def base_jid(jid: str) -> str:
    user, server = jid.split("@", 1)
    return f"{user.split(':')[0]}@{server}"


def make_msg_id() -> str:
    return "3EB0" + os.urandom(8).hex().upper()


def apply_forward_to_context(
    context_info,
    forward: bool | int = False,
    forwarding_score: int | None = None,
) -> bool:
    """
    Aplica etiqueta de mensaje reenviado (is_forwarded + forwarding_score) en ContextInfo.
    - forward=True  -> "Reenviado" (score=1)
    - forward=5     -> "Reenviado muchas veces" (score=5)
    - forwarding_score=5 -> fija el puntaje explícitamente
    """
    if not forward and forwarding_score is None:
        return False

    if isinstance(forward, bool):
        score = forwarding_score if forwarding_score is not None else (1 if forward else 0)
        is_fwd = forward or (score > 0)
    else:
        score = forwarding_score if forwarding_score is not None else int(forward)
        is_fwd = score > 0

    if not is_fwd:
        return False

    context_info.is_forwarded = True
    context_info.forwarding_score = max(1, int(score))
    return True


def get_contact_devices(signal_session, to_jid: str) -> list[str]:
    """Devuelve todos los dispositivos con sesión activa que pertenecen al mismo usuario."""
    base = base_jid(to_jid)
    base_user, base_server = base.split("@", 1)
    devices = []
    for jid in signal_session.sessions.keys():
        if "@" not in jid:
            continue
        u, s = jid.split("@", 1)
        if s == base_server and u.split(":")[0] == base_user:
            devices.append(jid)
    if to_jid not in devices:
        devices.append(to_jid)
    return devices


async def send_node(ws, transport, node: BinaryNode, debug: bool = False):
    if not ws or not transport:
        raise RuntimeError("No hay conexión activa con WhatsApp.")
    encoded = b"\x00" + encode_binary_node(node)
    encrypted = transport.encrypt(encoded)
    length_prefix = struct.pack(">I", len(encrypted))[1:]
    await ws.send(length_prefix + encrypted)
    if debug:
        print(f"[>>> ENVIADO] {node}")


async def relay_message(
    ws,
    transport,
    signal_session,
    to_jid: str,
    wa_msg: WAMessage | bytes,
    msg_type: str = "text",
    target_participants: list[str] | None = None,
    extra_attrs: dict[str, str] | None = None,
    enc_extra_attrs: dict[str, str] | None = None,
    debug: bool = False,
) -> str:
    """
    Cifra y envía cualquier WAMessage (o bytes proto ya serializados) a un chat individual
    (multi-dispositivo) o a un grupo (skmsg + distribución de SenderKey).
    """
    if not signal_session:
        raise RuntimeError("El motor Signal no está inicializado.")

    raw_proto = wa_msg if isinstance(wa_msg, (bytes, bytearray)) else wa_msg.SerializeToString()
    group = is_group(to_jid)
    base_to = base_jid(to_jid)
    msg_id = make_msg_id()

    if group:
        skmsg_bytes, skdm_bytes = signal_session.encrypt_skmsg(base_to, bytes(raw_proto))

        skdm_wa = WAMessage()
        skdm_wa.sender_key_distribution_message.group_id = base_to
        skdm_wa.sender_key_distribution_message.axolotl_sender_key_distribution_message = skdm_bytes
        skdm_proto = skdm_wa.SerializeToString()

        enc_msg_attrs = {"v": "2", "type": "msg"}
        if msg_type == "reaction":
            enc_msg_attrs["decrypt-fail"] = "hide"

        participant_nodes = []
        jids_to_notify = set(target_participants or []) | set(signal_session.sessions.keys())
        uses_lid = any(j.endswith("@lid") for j in jids_to_notify)

        for p_jid in jids_to_notify:
            if p_jid in signal_session.sessions:
                try:
                    enc_skdm = signal_session.encrypt_msg(p_jid, skdm_proto)
                    participant_nodes.append(
                        BinaryNode(
                            tag="to",
                            attrs={"jid": p_jid},
                            content=[
                                BinaryNode(tag="enc", attrs=dict(enc_msg_attrs), content=enc_skdm)
                            ],
                        )
                    )
                except Exception:
                    pass

        children = []
        if msg_type == "reaction":
            children.append(BinaryNode(tag="meta", attrs={"content_type": "add_on"}))
        if participant_nodes:
            children.append(BinaryNode(tag="participants", content=participant_nodes))

        skmsg_attrs = {"v": "2", "type": "skmsg"}
        if msg_type == "reaction":
            skmsg_attrs["decrypt-fail"] = "hide"
        if enc_extra_attrs:
            skmsg_attrs.update(enc_extra_attrs)

        children.append(BinaryNode(tag="enc", attrs=skmsg_attrs, content=skmsg_bytes))

        msg_attrs = {"id": msg_id, "to": base_to, "type": msg_type}
        if uses_lid:
            msg_attrs["addressing_mode"] = "lid"
        if extra_attrs:
            msg_attrs.update(extra_attrs)

        node = BinaryNode(
            tag="message",
            attrs=msg_attrs,
            content=children,
        )
    else:
        devices = get_contact_devices(signal_session, to_jid)
        participant_nodes = []
        enc_attrs = {"v": "2", "type": "msg"}
        if msg_type == "reaction":
            enc_attrs["decrypt-fail"] = "hide"
        if enc_extra_attrs:
            enc_attrs.update(enc_extra_attrs)

        for dev_jid in devices:
            try:
                enc_bytes = signal_session.encrypt_msg(dev_jid, bytes(raw_proto))
                participant_nodes.append(
                    BinaryNode(
                        tag="to",
                        attrs={"jid": dev_jid},
                        content=[
                            BinaryNode(tag="enc", attrs=dict(enc_attrs), content=enc_bytes)
                        ],
                    )
                )
            except Exception as e:
                print(f"[!] No se pudo cifrar ({msg_type}) para {dev_jid}: {e}")

        if not participant_nodes:
            raise RuntimeError(f"No hay sesión Signal activa para {to_jid}")

        msg_attrs = {"id": msg_id, "to": base_to, "type": msg_type}
        if extra_attrs:
            msg_attrs.update(extra_attrs)

        node = BinaryNode(
            tag="message",
            attrs=msg_attrs,
            content=[BinaryNode(tag="participants", content=participant_nodes)],
        )

    await send_node(ws, transport, node, debug)
    return msg_id