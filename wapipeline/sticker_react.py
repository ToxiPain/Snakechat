# wapipeline/sticker_react.py — Reacción con sticker (Sticker Annotation)
import asyncio
import time
from pathlib import Path
from typing import Any

from protobuf.media_pb2 import build_sticker_reaction_proto
from .media import load_media_bytes, prepare_sticker_webp, upload_media_file
from .transport import base_jid, is_group, relay_message


def _resolve_target(
    target: Any,
    target_msg_id: str | None,
    target_sender: str | None,
    from_me: bool | None,
) -> tuple[str | None, str | None, bool]:
    """Extrae (msg_id, sender_jid, from_me) desde IncomingMessage, QuotedMessage, dict o str."""
    if target is None:
        return target_msg_id, target_sender, bool(from_me) if from_me is not None else False

    if isinstance(target, str):
        return target, target_sender, bool(from_me) if from_me is not None else False

    if isinstance(target, dict):
        m_id = target.get("id") or target.get("stanza_id") or target_msg_id
        m_sender = target.get("sender") or target.get("participant") or target_sender
        m_from_me = target.get("from_me") if from_me is None else from_me
        return m_id, m_sender, bool(m_from_me) if m_from_me is not None else False

    m_id = getattr(target, "id", None) or getattr(target, "stanza_id", None) or target_msg_id
    m_sender = getattr(target, "sender", None) or getattr(target, "participant", None) or target_sender
    obj_from_me = getattr(target, "from_me", None)
    resolved_from_me = bool(from_me) if from_me is not None else bool(obj_from_me)
    return m_id, m_sender, resolved_from_me


async def sticker_react(
    ws,
    transport,
    signal_session,
    pending_iqs: dict[str, asyncio.Future],
    to_jid: str,
    target: Any,
    sticker: str | Path | bytes,
    *,
    target_msg_id: str | None = None,
    target_sender: str | None = None,
    from_me: bool | None = None,
    is_animated: bool = False,
    media_conn_cache: dict | None = None,
    debug: bool = False,
) -> str:
    """
    Reacciona a un mensaje con un sticker (Sticker Annotation).
    Acepta archivo local, URL (http/https) o bytes.
    """
    m_id, m_sender, is_from_me = _resolve_target(target, target_msg_id, target_sender, from_me)
    if not m_id:
        raise ValueError("sticker_react requiere target (IncomingMessage/QuotedMessage/msg_id).")

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

    group = is_group(to_jid)
    base_to = base_jid(to_jid)
    parent_participant = base_jid(m_sender) if (group and not is_from_me and m_sender) else None

    raw_proto = build_sticker_reaction_proto(
        url=uploaded["url"],
        direct_path=uploaded["direct_path"],
        media_key=uploaded["media_key"],
        file_sha256=uploaded["file_sha256"],
        file_enc_sha256=uploaded["file_enc_sha256"],
        file_length=uploaded["file_length"],
        media_key_timestamp=uploaded["media_key_timestamp"],
        parent_remote_jid=base_to,
        parent_msg_id=m_id,
        parent_from_me=is_from_me,
        parent_participant=parent_participant,
        width=width,
        height=height,
        is_animated=is_animated,
        sticker_sent_ts=int(time.time() * 1000),
    )

    participants = [m_sender] if m_sender else None

    msg_id = await relay_message(
        ws=ws,
        transport=transport,
        signal_session=signal_session,
        to_jid=to_jid,
        wa_msg=raw_proto,
        msg_type="media",
        target_participants=participants,
        enc_extra_attrs={"mediatype": "sticker"},
        debug=debug,
    )
    destino = "GRUPO" if group else "CHAT"
    print(f"[>>> STICKER REACT ({destino})] sobre msg_id={m_id} en {to_jid} (id={msg_id})")
    return msg_id