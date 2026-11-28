# protobuf/media_pb2.py — Serialización protobuf para StickerMessage y Sticker Annotation
import os


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


def _encode_message_key(
    remote_jid: str,
    msg_id: str,
    from_me: bool = False,
    participant: str | None = None,
) -> bytes:
    out = bytearray()
    if remote_jid:
        out.extend(_field_str(1, remote_jid))
    out.extend(_field_varint(2, 1 if from_me else 0))
    if msg_id:
        out.extend(_field_str(3, msg_id))
    if participant:
        out.extend(_field_str(4, participant))
    return bytes(out)


def _encode_sticker_message(
    *,
    url: str,
    direct_path: str,
    media_key: bytes,
    file_sha256: bytes,
    file_enc_sha256: bytes,
    file_length: int,
    media_key_timestamp: int,
    width: int = 512,
    height: int = 512,
    mimetype: str = "image/webp",
    is_animated: bool = False,
    context_info_bytes: bytes | None = None,
    sticker_sent_ts: int | None = None,
) -> bytes:
    out = bytearray()
    out.extend(_field_str(1, url))
    out.extend(_field_bytes(2, file_sha256))
    out.extend(_field_bytes(3, file_enc_sha256))
    out.extend(_field_bytes(4, media_key))
    out.extend(_field_str(5, mimetype))
    out.extend(_field_varint(6, height))
    out.extend(_field_varint(7, width))
    out.extend(_field_str(8, direct_path))
    out.extend(_field_varint(9, file_length))
    out.extend(_field_varint(10, media_key_timestamp))
    if is_animated:
        out.extend(_field_varint(13, 1))
    if context_info_bytes:
        out.extend(_field_bytes(17, context_info_bytes))
    if sticker_sent_ts is not None:
        out.extend(_field_varint(18, sticker_sent_ts))
    return bytes(out)


def _encode_message_association(
    parent_remote_jid: str,
    parent_msg_id: str,
    parent_from_me: bool = False,
    parent_participant: str | None = None,
    association_type: int = 11,  # STICKER_ANNOTATION
) -> bytes:
    parent_key = _encode_message_key(
        remote_jid=parent_remote_jid,
        msg_id=parent_msg_id,
        from_me=parent_from_me,
        participant=parent_participant,
    )
    out = bytearray()
    out.extend(_field_varint(1, association_type))
    out.extend(_field_bytes(2, parent_key))
    return bytes(out)


def build_sticker_proto(
    *,
    url: str,
    direct_path: str,
    media_key: bytes,
    file_sha256: bytes,
    file_enc_sha256: bytes,
    file_length: int,
    media_key_timestamp: int,
    width: int = 512,
    height: int = 512,
    is_animated: bool = False,
    context_info_bytes: bytes | None = None,
    sticker_sent_ts: int | None = None,
) -> bytes:
    """Construye un WAMessage serializado con StickerMessage (field 26)."""
    sticker_bytes = _encode_sticker_message(
        url=url,
        direct_path=direct_path,
        media_key=media_key,
        file_sha256=file_sha256,
        file_enc_sha256=file_enc_sha256,
        file_length=file_length,
        media_key_timestamp=media_key_timestamp,
        width=width,
        height=height,
        is_animated=is_animated,
        context_info_bytes=context_info_bytes,
        sticker_sent_ts=sticker_sent_ts,
    )
    return _field_bytes(26, sticker_bytes)


def build_sticker_reaction_proto(
    *,
    url: str,
    direct_path: str,
    media_key: bytes,
    file_sha256: bytes,
    file_enc_sha256: bytes,
    file_length: int,
    media_key_timestamp: int,
    parent_remote_jid: str,
    parent_msg_id: str,
    parent_from_me: bool = False,
    parent_participant: str | None = None,
    width: int = 512,
    height: int = 512,
    is_animated: bool = False,
    sticker_sent_ts: int | None = None,
    message_secret: bytes | None = None,
) -> bytes:
    """
    Construye un WAMessage serializado con:
      - field 26: StickerMessage
      - field 35: MessageContextInfo (messageSecret=3 + messageAssociation=10 con STICKER_ANNOTATION=11)
    """
    sticker_bytes = _encode_sticker_message(
        url=url,
        direct_path=direct_path,
        media_key=media_key,
        file_sha256=file_sha256,
        file_enc_sha256=file_enc_sha256,
        file_length=file_length,
        media_key_timestamp=media_key_timestamp,
        width=width,
        height=height,
        is_animated=is_animated,
        sticker_sent_ts=sticker_sent_ts,
    )

    secret = message_secret or os.urandom(32)
    assoc_bytes = _encode_message_association(
        parent_remote_jid=parent_remote_jid,
        parent_msg_id=parent_msg_id,
        parent_from_me=parent_from_me,
        parent_participant=parent_participant,
        association_type=11,
    )

    msg_ctx = bytearray()
    msg_ctx.extend(_field_bytes(3, secret))       # messageSecret
    msg_ctx.extend(_field_bytes(10, assoc_bytes)) # messageAssociation

    wa_msg = bytearray()
    wa_msg.extend(_field_bytes(26, sticker_bytes))
    wa_msg.extend(_field_bytes(35, bytes(msg_ctx)))
    return bytes(wa_msg)