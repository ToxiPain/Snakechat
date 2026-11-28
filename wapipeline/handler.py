# Handler de nodos entrantes: despacha cada tag y muestra mensajes en consola
from binary import BinaryNode
from protobuf import WAMessage
from .transport import send_node
from .receive import (
    build_ack,
    build_retry_receipt,
    extract_forward_info,
    extract_group_mentions,
    extract_mentions,
    extract_quoted,
    extract_text,
)
from .connection import IncomingMessage, QuotedMessage


def _print_incoming(node: BinaryNode, sender: str, chat_jid: str, text: str):
    push_name = node.attrs.get("notify", "")
    msg_id = node.attrs.get("id", "")
    es_grupo = "@g.us" in chat_jid
    label = f"{push_name} ({sender})" if push_name else sender
    tipo = "[GRUPO]" if es_grupo else "[CHAT]"
    print(f"{tipo} [<<< MENSAJE de {label}] {text!r}  (id={msg_id})")


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
        print(f"[<<< ACK SERVIDOR] {node}")
        return False

    if node.tag == "stream:error" and node.attrs.get("code") == "515":
        print("[*] Reinicio de stream (515). Reconectando...")
        return True

    if node.tag in ("notification", "receipt", "call"):
        if node.tag == "receipt":
            print(f"[<<< RECIBO] {node}")
        await send_node(client._ws, client._transport, build_ack(node))
        if node.tag == "notification" and node.attrs.get("type") == "encrypt":
            await _handle_prekey_refill(node, client)
        return False

    if node.tag == "message":
        await _handle_message(node, client)
        return False

    reply = client.pairing.handle_node(node)
    if reply is not None:
        await send_node(client._ws, client._transport, reply)
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
                f"[<<< REACCIÓN DESCIFRADA de {sender}] "
                f"emoji={r.text!r} remote_jid={r.key.remote_jid!r} "
                f"participant={r.key.participant!r} from_me={r.key.from_me} "
                f"target_id={r.key.id!r} ts={r.sender_timestamp_ms}"
            )
    except Exception:
        pass


async def _handle_message(node: BinaryNode, client):
    chat_jid = node.attrs.get("from", "")
    sender = node.attrs.get("participant") or chat_jid
    is_group = "@g.us" in chat_jid
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
                if is_group:
                    _try_extract_skdm(plain, chat_jid, sender, client.signal)
                _log_reaction_if_present(plain, sender)
                text = extract_text(plain)
                mentioned_jids = extract_mentions(plain)
                g_mentions = extract_group_mentions(plain)
                quoted = extract_quoted(plain, chat_jid, my_jids=my_jids)
                is_forwarded, forwarding_score = extract_forward_info(plain)

            elif enc_type == "msg":
                plain = client.signal.decrypt_msg(sender, enc.content)
                if is_group:
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