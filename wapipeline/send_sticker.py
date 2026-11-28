# wapipeline/send_sticker.py — Envío de stickers normales (archivo local, URL o bytes)
import asyncio
import time
from pathlib import Path
from typing import Any

from protobuf import WAMessage
from protobuf.media_pb2 import build_sticker_proto
from .media import load_media_bytes, prepare_sticker_webp, upload_media_file
from .transport import apply_forward_to_context, base_jid, is_group, relay_message
from .mention_user import apply_mentions_to_context
from .mention_group import apply_group_mentions_to_context
from .reply_msg import _resolve_quote


async def send_sticker(
    ws,
    transport,
    signal_session,
    pending_iqs: dict[str, asyncio.Future],
    to_jid: str,
    sticker: str | Path | bytes,
    *,
    quoted: Any = None,
    quoted_msg_id: str | None = None,
    quoted_sender: str | None = None,
    quoted_text: str | None = None,
    tag: Any = None,
    g_tag: Any = None,
    forward: bool | int = False,
    forwarding_score: int | None = None,
    is_animated: bool = False,
    media_conn_cache: dict | None = None,
    debug: bool = False,
) -> str:
    """
    Envía un sticker normal desde un archivo local, una URL (http/https) o bytes.

    Ejemplos:
        await client.send_sticker(chat_jid, "src/prueba.png")
        await client.send_sticker(chat_jid, "https://ejemplo.com/imagen.png", quoted=umsg)
    """
    raw_bytes = await load_media_bytes(sticker)
    webp_bytes, width, height = await asyncio.to_thread(prepare_sticker_webp, raw_bytes)

    uploaded = await upload_media_file(
        ws=ws,
        transport=transport,
        pending_iqs=pending_iqs,
        data=webp_bytes,
        media_type="sticker",
        media_conn_cache=media_conn_cache,
        debug=debug,
    )

    context_info_bytes: bytes | None = None
    target_participants: list[str] = []

    has_quote = bool(quoted is not None or quoted_msg_id or quoted_sender or quoted_text)
    has_ctx = bool(has_quote or tag or g_tag or forward or forwarding_score is not None)
    if has_ctx:
        tmp_wa = WAMessage()
        ctx = tmp_wa.extended_text_message.context_info
        if has_quote:
            q_id, q_sender, q_text = _resolve_quote(quoted, quoted_msg_id, quoted_sender, quoted_text)
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
        context_info_bytes = ctx.SerializeToString()

    raw_proto = build_sticker_proto(
        url=uploaded["url"],
        direct_path=uploaded["direct_path"],
        media_key=uploaded["media_key"],
        file_sha256=uploaded["file_sha256"],
        file_enc_sha256=uploaded["file_enc_sha256"],
        file_length=uploaded["file_length"],
        media_key_timestamp=uploaded["media_key_timestamp"],
        width=width,
        height=height,
        is_animated=is_animated,
        context_info_bytes=context_info_bytes,
        sticker_sent_ts=int(time.time() * 1000),
    )

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=raw_proto,
        msg_type="media",
        target_participants=target_participants or None,
        enc_extra_attrs={"mediatype": "sticker"},
        debug=debug,
    )
    destino = "GRUPO" if is_group(to_jid) else "CHAT"
    print(f"[>>> STICKER ENVIADO ({destino}) a {to_jid}] (id={msg_id})")
    return msg_id