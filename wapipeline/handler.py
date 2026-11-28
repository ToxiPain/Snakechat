# wapipeline/handler.py — Handler de nodos + estado de conexión + capa de transporte
# (Consolida: handler.py original + connection.py + transport.py)
import asyncio
import os
import struct
from dataclasses import dataclass, field

from binary import BinaryNode, encode_binary_node
from protobuf import WAMessage
from .receive import (
    build_ack,
    build_retry_receipt,
    extract_forward_info,
    extract_group_mentions,
    extract_mentions,
    extract_quoted,
    extract_text,
)


# ══════════════════════════════════════════════════════════════════════════════
#  TRANSPORTE — funciones de cifrado y envío de nodos
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  MODELOS DE CONEXIÓN — IncomingMessage, QuotedMessage, keepalive
# ══════════════════════════════════════════════════════════════════════════════

def _split_jid(jid: str | None) -> tuple[str | None, str | None, str | None]:
    """Devuelve (user_base, device, server) a partir de un JID."""
    if not jid or "@" not in jid:
        return None, None, None
    user_part, server = jid.split("@", 1)
    if ":" in user_part:
        user_base, dev = user_part.split(":", 1)
        return user_base, dev, server
    return user_part, None, server


def _base_jid(jid: str | None) -> str | None:
    user_base, _, server = _split_jid(jid)
    if not user_base or not server:
        return jid
    return f"{user_base}@{server}"


@dataclass
class QuotedMessage:
    id: str
    sender: str
    chat_jid: str
    text: str | None = None
    from_me: bool = False

    @property
    def is_group(self) -> bool:
        return "@g.us" in self.chat_jid

    @property
    def sender_base(self) -> str:
        return _base_jid(self.sender) or self.sender

    @property
    def lid(self) -> str | None:
        _, _, server = _split_jid(self.sender)
        if server == "lid":
            return _base_jid(self.sender)
        return None

    @property
    def jid(self) -> str | None:
        _, _, server = _split_jid(self.sender)
        if server == "s.whatsapp.net":
            return _base_jid(self.sender)
        return None

    @property
    def number(self) -> str | None:
        num_jid = self.jid
        if not num_jid:
            return None
        user_base, _, _ = _split_jid(num_jid)
        return user_base


@dataclass
class IncomingMessage:
    id: str
    sender: str                        # JID del remitente (individual o participante en grupo)
    chat_jid: str                      # JID del chat (= sender en individual, grupo en @g.us)
    sender_pn: str | None = None       # JID de teléfono (sender_pn o participant_pn)
    push_name: str | None = None       # Nombre visible (notify)
    text: str | None = None
    addressing_mode: str | None = None
    mentioned_jids: list[str] = field(default_factory=list)
    g_mentions: list[dict[str, str]] = field(default_factory=list)
    quoted: QuotedMessage | None = None
    is_forwarded: bool = False
    forwarding_score: int = 0
    raw_node: BinaryNode | None = None

    @property
    def is_group(self) -> bool:
        return "@g.us" in self.chat_jid

    @property
    def sender_base(self) -> str:
        return _base_jid(self.sender) or self.sender

    @property
    def device(self) -> str | None:
        _, dev, _ = _split_jid(self.sender)
        return dev

    @property
    def lid(self) -> str | None:
        _, _, server = _split_jid(self.sender)
        if server == "lid":
            return _base_jid(self.sender)
        return None

    @property
    def jid(self) -> str | None:
        """JID de número (@s.whatsapp.net) si está disponible en el mensaje."""
        _, _, server = _split_jid(self.sender)
        if server == "s.whatsapp.net":
            return _base_jid(self.sender)
        if self.sender_pn and "@s.whatsapp.net" in self.sender_pn:
            return _base_jid(self.sender_pn)
        return None

    @property
    def pn(self) -> str | None:
        return self.jid

    @property
    def number(self) -> str | None:
        """Número de teléfono extraído del JID @s.whatsapp.net, si existe."""
        num_jid = self.jid
        if not num_jid:
            return None
        user_base, _, _ = _split_jid(num_jid)
        return user_base


async def keepalive_loop(ws, transport, debug: bool = False):
    seq = 1
    try:
        while True:
            await asyncio.sleep(25)
            ping = BinaryNode(
                tag="iq",
                attrs={
                    "id": f"ping-{seq}",
                    "to": "s.whatsapp.net",
                    "type": "get",
                    "xmlns": "w:p",
                },
                content=[BinaryNode(tag="ping")],
            )
            await send_node(ws, transport, ping, debug)
            if debug:
                print(f"[*] Keep-Alive ping-{seq} enviado.")
            seq += 1
    except asyncio.CancelledError:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLER — despacho de nodos entrantes
# ══════════════════════════════════════════════════════════════════════════════

def _print_incoming(node: BinaryNode, sender: str, chat_jid: str, text: str):
    push_name = node.attrs.get("notify", "")
    msg_id = node.attrs.get("id", "")
    es_grupo = "@g.us" in chat_jid
    label = f"{push_name} ({sender})" if push_name else sender
    tipo = "[GRUPO]" if es_grupo else "[CHAT]"
    print(f"{tipo} [MSG: {label}] {text!r}  (id={msg_id})")


async def handle_node(node: BinaryNode, client) -> bool:
    if node.tag == "success":
        return False

    if node.tag == "iq" and node.attrs.get("type") in ("result", "error"):
        iq_id = node.attrs.get("id")
        pending = getattr(client, "_pending_iqs", None)
        if iq_id and pending and iq_id in pending:
            fut = pending[iq_id]
            if not fut.done():
                fut.set_result(node)
            return False

    if node.tag == "ack" and node.attrs.get("class") == "message":
        print(f"[ACK] {node}")
        return False

    if node.tag == "stream:error" and node.attrs.get("code") == "515":
        print("[*] Reinicio de stream (515). Reconectando...")
        return True

    if node.tag in ("notification", "receipt", "call"):
        if node.tag == "receipt":
            print(f"[RECIBED] {node}")
        await send_node(client._ws, client._transport, build_ack(node))
        if node.tag == "notification":
            notif_type = node.attrs.get("type")
            if notif_type == "encrypt":
                await _handle_prekey_refill(node, client)
            elif notif_type == "link_code_companion_reg" or node.get_child("link_code_companion_reg"):
                finish_iq = client.pairing.handle_link_code_primary_hello(node)
                if finish_iq is not None:
                    await send_node(client._ws, client._transport, finish_iq, client.debug)
        return False

    if node.tag == "message":
        await _handle_message(node, client)
        return False

    use_pair_code = bool(getattr(client, "phone_number", None)) and not client.pairing.is_registered
    is_pair_device = node.tag == "iq" and node.attrs.get("type") == "set" and node.get_child("pair-device") is not None

    reply = client.pairing.handle_node(node, suppress_qr=use_pair_code)
    if reply is not None:
        await send_node(client._ws, client._transport, reply, client.debug)

    if is_pair_device and use_pair_code and not getattr(client, "_pairing_code_requested", False):
        client._pairing_code_requested = True
        asyncio.create_task(client.request_pairing_code(client.phone_number))

    return False


async def _handle_prekey_refill(node: BinaryNode, client):
    count_node = node.get_child("count")
    if count_node and int(count_node.attrs.get("value", "0")) < 10:
        client._prekey_seq = getattr(client, "_prekey_seq", 1)
        iq_id = f"upload-prekeys-{client._prekey_seq}"
        client._prekey_seq += 1
        upload_iq = client.prekeys.build_upload_iq(
            iq_id=iq_id,
            reg_id=client.pairing.reg_id,
            ident_priv_bytes=client.pairing.ident_priv_bytes,
            ident_pub_bytes=client.pairing.ident_pub_bytes,
            skey_pub_bytes=client.pairing.skey_pub_bytes,
            count=30,
        )
        await send_node(client._ws, client._transport, upload_iq, client.debug)


def _try_extract_skdm(plain: bytes, group_jid: str, sender: str, signal) -> bool:
    try:
        wa = WAMessage()
        wa.ParseFromString(plain)
        if wa.HasField("sender_key_distribution_message"):
            skdm_inner = wa.sender_key_distribution_message.axolotl_sender_key_distribution_message
            if skdm_inner:
                signal.process_sender_key_distribution(group_jid, sender, skdm_inner)
                return True
    except Exception:
        pass
    return False


def _log_reaction_if_present(plain: bytes, sender: str):
    try:
        wa = WAMessage()
        wa.ParseFromString(plain)
        if wa.HasField("react_message"):
            r = wa.react_message
            print(
                f"[REACT: {sender}] "
                f"emoji={r.text!r} remote_jid={r.key.remote_jid!r} "
                f"participant={r.key.participant!r} from_me={r.key.from_me} "
                f"target_id={r.key.id!r} ts={r.sender_timestamp_ms}"
            )
    except Exception:
        pass


async def _handle_message(node: BinaryNode, client):
    chat_jid = node.attrs.get("from", "")
    sender = node.attrs.get("participant") or chat_jid
    is_grp = "@g.us" in chat_jid
    my_jids = [client.pairing.jid, client.pairing.lid]

    enc = node.get_child("enc")
    text = None
    mentioned_jids: list[str] = []
    g_mentions: list[dict[str, str]] = []
    quoted: QuotedMessage | None = None
    is_forwarded = False
    forwarding_score = 0
    decrypt_failed = False

    if enc and isinstance(enc.content, bytes):
        enc_type = enc.attrs.get("type")

        try:
            if enc_type == "pkmsg":
                plain = client.signal.decrypt_pkmsg(sender, enc.content)
                if is_grp:
                    _try_extract_skdm(plain, chat_jid, sender, client.signal)
                _log_reaction_if_present(plain, sender)
                text = extract_text(plain)
                mentioned_jids = extract_mentions(plain)
                g_mentions = extract_group_mentions(plain)
                quoted = extract_quoted(plain, chat_jid, my_jids=my_jids)
                is_forwarded, forwarding_score = extract_forward_info(plain)

            elif enc_type == "msg":
                plain = client.signal.decrypt_msg(sender, enc.content)
                if is_grp:
                    _try_extract_skdm(plain, chat_jid, sender, client.signal)
                _log_reaction_if_present(plain, sender)
                text = extract_text(plain)
                mentioned_jids = extract_mentions(plain)
                g_mentions = extract_group_mentions(plain)
                quoted = extract_quoted(plain, chat_jid, my_jids=my_jids)
                is_forwarded, forwarding_score = extract_forward_info(plain)

            elif enc_type == "skmsg":
                try:
                    plain = client.signal.decrypt_skmsg(chat_jid, sender, enc.content)
                    _log_reaction_if_present(plain, sender)
                    text = extract_text(plain)
                    mentioned_jids = extract_mentions(plain)
                    g_mentions = extract_group_mentions(plain)
                    quoted = extract_quoted(plain, chat_jid, my_jids=my_jids)
                    is_forwarded, forwarding_score = extract_forward_info(plain)
                except ValueError as ve:
                    if "No hay sender key" in str(ve):
                        print(f"[!] Sender key ausente para {sender} en {chat_jid}. Pidiendo retry...")
                        decrypt_failed = True
                    else:
                        raise
            else:
                print(f"[!] Tipo de enc desconocido: {enc_type!r} de {sender}")

        except Exception as e:
            decrypt_failed = True
            print(f"[!] Error descifrando ({enc_type}) de {sender}: {e}")

    await send_node(client._ws, client._transport, build_ack(node))

    if decrypt_failed:
        print(f"[*] Solicitando reenvío (retry + keys) a {sender}...")
        await send_node(
            client._ws, client._transport,
            build_retry_receipt(node, client.pairing, client.prekeys),
        )
        return

    if text is not None:
        _print_incoming(node, sender, chat_jid, text)
        sender_pn = node.attrs.get("sender_pn") or node.attrs.get("participant_pn")
        umsg = IncomingMessage(
            id=node.attrs.get("id", ""),
            sender=sender,
            chat_jid=chat_jid,
            sender_pn=sender_pn,
            push_name=node.attrs.get("notify"),
            text=text,
            addressing_mode=node.attrs.get("addressing_mode"),
            mentioned_jids=mentioned_jids,
            g_mentions=g_mentions,
            quoted=quoted,
            is_forwarded=is_forwarded,
            forwarding_score=forwarding_score,
            raw_node=node,
        )
        await client._emit("message", umsg)