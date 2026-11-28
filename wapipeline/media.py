# wapipeline/media.py — Pipeline global de media: carga local/URL, media_conn, cifrado HKDF/AES-CBC, WebP y upload MMG
import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from binary import BinaryNode
from .transport import send_node

MEDIA_HKDF_INFO = {
    "image": b"WhatsApp Image Keys",
    "sticker": b"WhatsApp Image Keys",
    "video": b"WhatsApp Video Keys",
    "audio": b"WhatsApp Audio Keys",
    "document": b"WhatsApp Document Keys",
}

MEDIA_PATH_MAP = {
    "image": "/mms/image",
    "sticker": "/mms/image",
    "video": "/mms/video",
    "audio": "/mms/audio",
    "document": "/mms/document",
}

MEDIA_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _download_url_sync(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": MEDIA_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


async def load_media_bytes(source: str | Path | bytes, timeout: float = 20.0) -> bytes:
    """Carga bytes desde una URL (http/https), una ruta local o bytes directamente."""
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)

    if isinstance(source, str):
        stripped = source.strip()
        if stripped.startswith(("http://", "https://")):
            return await asyncio.to_thread(_download_url_sync, stripped, timeout)
        path = Path(stripped)
    else:
        path = source

    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")
    return await asyncio.to_thread(path.read_bytes)


async def send_iq_and_wait(
    ws,
    transport,
    pending_iqs: dict[str, asyncio.Future],
    iq_node: BinaryNode,
    debug: bool = False,
    timeout: float = 15.0,
) -> BinaryNode:
    iq_id = iq_node.attrs["id"]
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    pending_iqs[iq_id] = fut
    try:
        await send_node(ws, transport, iq_node, debug)
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        pending_iqs.pop(iq_id, None)


async def request_media_conn(
    ws,
    transport,
    pending_iqs: dict[str, asyncio.Future],
    cache: dict | None = None,
    debug: bool = False,
) -> dict:
    """Obtiene (o reutiliza si no expiró) el auth y los hosts de subida media_conn."""
    now = time.time()
    if cache and cache.get("expires_at", 0) > now + 30:
        return cache

    iq_node = BinaryNode(
        tag="iq",
        attrs={
            "id": "mconn-" + os.urandom(6).hex(),
            "xmlns": "w:m",
            "type": "set",
            "to": "s.whatsapp.net",
        },
        content=[BinaryNode(tag="media_conn")],
    )
    resp = await send_iq_and_wait(ws, transport, pending_iqs, iq_node, debug=debug)
    if resp.attrs.get("type") == "error":
        raise RuntimeError(f"WhatsApp rechazó media_conn: {resp}")

    mc = resp.get_child("media_conn")
    if not mc:
        raise RuntimeError(f"Respuesta sin nodo <media_conn>: {resp}")

    auth = mc.attrs.get("auth", "")
    ttl = int(mc.attrs.get("ttl", "300"))
    hosts = [h.attrs["hostname"] for h in mc.get_children("host") if h.attrs.get("hostname")]
    if not auth or not hosts:
        raise RuntimeError(f"media_conn incompleto: {mc}")

    result = {
        "auth": auth,
        "hosts": hosts,
        "expires_at": now + ttl,
    }
    if cache is not None:
        cache.clear()
        cache.update(result)
    return result


def prepare_sticker_webp(source: str | Path | bytes) -> tuple[bytes, int, int]:
    """
    Convierte una imagen (bytes o ruta local) a WebP 512x512 si no es WebP.
    Retorna (webp_bytes, width, height).
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de sticker: {path}")
        raw = path.read_bytes()
    else:
        raw = bytes(source)

    # Si ya es WebP, devolver directo
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return raw, 512, 512

    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Se necesita Pillow para convertir PNG/JPG a sticker WebP: py -m pip install Pillow"
        ) from e

    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGBA")
        img.thumbnail((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        offset = ((512 - img.width) // 2, (512 - img.height) // 2)
        canvas.paste(img, offset, img)
        out = io.BytesIO()
        canvas.save(out, format="WEBP", quality=80, method=6)
        return out.getvalue(), 512, 512


def encrypt_media(data: bytes, media_type: str = "sticker") -> dict:
    """Cifra un archivo con el esquema estándar de WhatsApp (HKDF + AES-256-CBC + HMAC-SHA256[:10])."""
    info = MEDIA_HKDF_INFO.get(media_type, b"WhatsApp Image Keys")
    media_key = os.urandom(32)
    expanded = HKDF(
        algorithm=hashes.SHA256(),
        length=112,
        salt=b"\x00" * 32,
        info=info,
    ).derive(media_key)

    iv = expanded[0:16]
    cipher_key = expanded[16:48]
    mac_key = expanded[48:80]

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()[:10]
    enc_data = ciphertext + mac

    return {
        "media_key": media_key,
        "media_key_timestamp": int(time.time()),
        "file_sha256": hashlib.sha256(data).digest(),
        "file_enc_sha256": hashlib.sha256(enc_data).digest(),
        "file_length": len(data),
        "enc_data": enc_data,
    }


def _http_upload_sync(
    hosts: list[str],
    auth: str,
    media_type: str,
    enc_data: bytes,
    file_enc_sha256: bytes,
) -> tuple[str, str]:
    path_prefix = MEDIA_PATH_MAP.get(media_type, "/mms/image")
    token = _b64url(file_enc_sha256)
    auth_q = urllib.parse.quote(auth, safe="")
    last_err: Exception | None = None

    for host in hosts:
        url = f"https://{host}{path_prefix}/{token}?auth={auth_q}&token={token}"
        req = urllib.request.Request(
            url,
            data=enc_data,
            method="POST",
            headers={
                "Content-Type": "application/octet-stream",
                "Origin": "https://web.whatsapp.com",
                "Referer": "https://web.whatsapp.com/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                media_url = body.get("url")
                direct_path = body.get("direct_path")
                if media_url and direct_path:
                    return media_url, direct_path
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Error subiendo media a WhatsApp MMG: {last_err}")


async def upload_media_file(
    ws,
    transport,
    pending_iqs: dict[str, asyncio.Future],
    data: bytes,
    media_type: str = "sticker",
    media_conn_cache: dict | None = None,
    debug: bool = False,
) -> dict:
    """Cifra y sube un archivo a los servidores MMG de WhatsApp."""
    mc = await request_media_conn(ws, transport, pending_iqs, cache=media_conn_cache, debug=debug)
    enc = encrypt_media(data, media_type=media_type)
    media_url, direct_path = await asyncio.to_thread(
        _http_upload_sync,
        mc["hosts"],
        mc["auth"],
        media_type,
        enc["enc_data"],
        enc["file_enc_sha256"],
    )
    enc["url"] = media_url
    enc["direct_path"] = direct_path
    return enc