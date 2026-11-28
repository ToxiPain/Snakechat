# Cliente principal SnakeChat: conexión WebSocket, Noise XX y bucle de eventos
import asyncio
import re
import struct
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Awaitable, Callable

import websockets
from cryptography.hazmat.primitives.asymmetric import x25519

from protobuf import HandshakeMessage
from crypto.keys import generate_x25519_keypair
from crypto.noise import NoiseTransport
from crypto.handshake import NoiseHandshakeState
from crypto.signal import SignalSessionManager
from state import PairingState, PreKeyStore
from binary import BinaryNode, decode_binary_node
from wapipeline.handler import (
    send_node,
    IncomingMessage,
    keepalive_loop,
    handle_node,
)
from wapipeline.media import send_iq_and_wait
from wapipeline.send_msg import (
    send_msg,
    send_text,
    mention_user,
    mention_group,
    tag_user as _tag_user,
    tag_group as _tag_group,
    normalize_mention_jids,
    normalize_group_mentions,
)
from wapipeline.edit_msg import edit_msg
from wapipeline.delete_msg import delete_msg
from wapipeline.read_msg import read_msg
from wapipeline.typing import (
    send_presence,
    send_typing,
    stop_typing,
    send_recording,
    stop_recording,
    set_online,
    set_offline,
)
from wapipeline.react_msg import react_msg
from wapipeline.send_sticker import send_sticker
from wapipeline.sticker_react import sticker_react

WA_WS_URL = "wss://web.whatsapp.com/ws/chat"
WA_ORIGIN = "https://web.whatsapp.com"
WA_HEADER = b"WA\x06\x03"
WA_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
FALLBACK_WA_VERSION = (2, 3000, 1056109635)


class SnakeChatClient:

    def __init__(self, debug: bool = False, phone_number: str | None = None):
        self.debug = debug
        self.phone_number = phone_number
        self.wa_version = self._fetch_latest_wa_version()
        self.pairing = PairingState(self.wa_version)
        self.prekeys = PreKeyStore()
        self.signal: SignalSessionManager | None = None

        self._ws = None
        self._transport: NoiseTransport | None = None
        self._handlers: dict[str, list[Callable[..., Awaitable[Any]]]] = defaultdict(list)
        self._pending_iqs: dict[str, asyncio.Future] = {}
        self._media_conn: dict = {}
        self._prekey_seq: int = 1
        self._pairing_code_requested: bool = False

    def on(self, event: str):
        def decorator(func: Callable[..., Awaitable[Any]]):
            self._handlers[event].append(func)
            return func
        return decorator

    async def _run_handler(self, event: str, handler: Callable[..., Awaitable[Any]], *args):
        try:
            await handler(*args)
        except Exception as e:
            print(f"[!] Error en handler de '{event}': {type(e).__name__}: {e}")

    async def _emit(self, event: str, *args):
        for handler in self._handlers.get(event, []):
            asyncio.create_task(self._run_handler(event, handler, *args))

    @staticmethod
    def _fetch_latest_wa_version() -> tuple[int, int, int]:
        try:
            req = urllib.request.Request(
                "https://web.whatsapp.com/sw.js",
                headers={"User-Agent": WA_USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            match = re.search(r'"client_revision"\s*:\s*(\d+)', text)
            if match:
                return (2, 3000, int(match.group(1)))
        except Exception:
            pass
        return FALLBACK_WA_VERSION

    @staticmethod
    def _build_frame(payload: bytes, include_header: bool = False) -> bytes:
        length_prefix = struct.pack(">I", len(payload))[1:]
        return (WA_HEADER + length_prefix + payload) if include_header else (length_prefix + payload)

    @staticmethod
    def _unpack_transport(raw_decrypted: bytes) -> bytes:
        if not raw_decrypted:
            return b""
        flags = raw_decrypted[0]
        data = raw_decrypted[1:]
        return zlib.decompress(data) if (flags & 2) else data

    # ------------------------------------------------------------------ #
    #  API pública                                                          #
    # ------------------------------------------------------------------ #

    async def request_pairing_code(self, phone_number: str, custom_code: str | None = None) -> str:
        """
        Solicita un código de emparejamiento de 8 dígitos para vincular sin QR.
        Ejemplo: await client.request_pairing_code("50557418454")
        """
        code, iq_node = self.pairing.build_pairing_code_iq(phone_number, custom_code=custom_code)
        resp = await send_iq_and_wait(
            self._ws,
            self._transport,
            self._pending_iqs,
            iq_node,
            debug=self.debug,
        )
        if resp.attrs.get("type") == "error":
            raise RuntimeError(f"WhatsApp rechazó el Pairing Code: {resp}")

        self.pairing.print_pairing_code(code, self.pairing.pairing_phone or phone_number)
        await self._emit("pairing_code", code)
        return code

    async def send_node(self, node: BinaryNode):
        """Envía un BinaryNode raw (uso avanzado)."""
        await send_node(self._ws, self._transport, node, self.debug)

    async def send_msg(
        self,
        to_jid: str,
        text: str,
        *,
        reply: Any = None,
        quoted_msg_id: str | None = None,
        quoted_sender: str | None = None,
        quoted_text: str | None = None,
        tag: Any = None,
        g_tag: Any = None,
        forward: bool | int = False,
        forwarding_score: int | None = None,
    ) -> str:
        """
        Envía texto a un chat individual o grupo.
        Usa reply=umsg para citar un mensaje (antes reply_msg).
        """
        return await send_msg(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            text,
            self.debug,
            reply=reply,
            quoted_msg_id=quoted_msg_id,
            quoted_sender=quoted_sender,
            quoted_text=quoted_text,
            tag=tag,
            g_tag=g_tag,
            forward=forward,
            forwarding_score=forwarding_score,
        )

    # Alias de compatibilidad hacia atrás
    async def send_text(
        self,
        to_jid: str,
        text: str,
        *,
        tag: Any = None,
        g_tag: Any = None,
        forward: bool | int = False,
        forwarding_score: int | None = None,
    ) -> str:
        return await self.send_msg(
            to_jid,
            text,
            tag=tag,
            g_tag=g_tag,
            forward=forward,
            forwarding_score=forwarding_score,
        )

    async def edit_msg(
        self,
        to_jid: str,
        target: Any,
        new_text: str,
        *,
        msg_id: str | None = None,
        tag: Any = None,
        g_tag: Any = None,
    ) -> str:
        """Edita un mensaje enviado previamente por el bot."""
        return await edit_msg(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            target,
            new_text,
            msg_id=msg_id,
            tag=tag,
            g_tag=g_tag,
            debug=self.debug,
        )

    async def delete_msg(
        self,
        to_jid: str,
        target: Any = None,
        *,
        msg_id: str | None = None,
        sender: str | None = None,
        from_me: bool | None = None,
    ) -> str:
        """Elimina un mensaje para todos (propio o de otro usuario si eres admin en grupo)."""
        return await delete_msg(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            target=target,
            msg_id=msg_id,
            sender=sender,
            from_me=from_me,
            debug=self.debug,
        )

    async def mention_user(
        self,
        to_jid: str,
        users: Any,
        text: str = "",
        *,
        ghost: bool = False,
        reply: Any = None,
        quoted_msg_id: str | None = None,
        quoted_sender: str | None = None,
        quoted_text: str | None = None,
        forward: bool | int = False,
        forwarding_score: int | None = None,
    ) -> str:
        """Menciona a uno o varios usuarios (con @ automático o modo ghost=True)."""
        return await mention_user(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            users,
            text,
            ghost=ghost,
            reply=reply,
            quoted_msg_id=quoted_msg_id,
            quoted_sender=quoted_sender,
            quoted_text=quoted_text,
            forward=forward,
            forwarding_score=forwarding_score,
            debug=self.debug,
        )

    async def mention_group(
        self,
        to_jid: str,
        groups: Any,
        text: str = "",
        *,
        group_subject: str | None = None,
        ghost: bool = False,
        tag: Any = None,
        reply: Any = None,
        quoted_msg_id: str | None = None,
        quoted_sender: str | None = None,
        quoted_text: str | None = None,
        forward: bool | int = False,
        forwarding_score: int | None = None,
    ) -> str:
        """Menciona a uno o varios grupos (@NombreDelGrupo) con soporte de ghost y reply."""
        return await mention_group(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            groups,
            text,
            group_subject=group_subject,
            ghost=ghost,
            tag=tag,
            reply=reply,
            quoted_msg_id=quoted_msg_id,
            quoted_sender=quoted_sender,
            quoted_text=quoted_text,
            forward=forward,
            forwarding_score=forwarding_score,
            debug=self.debug,
        )

    def tag_user(self, user: Any) -> str:
        """Devuelve el token '@<número>' para mencionar a un usuario en el texto del mensaje."""
        return _tag_user(user)

    def tag_group(self, group: Any) -> str:
        """Devuelve el token '@<id>@g.us' para mencionar a un grupo en el texto del mensaje."""
        return _tag_group(group)

    async def read_msg(
        self,
        target: Any = None,
        sender_jid: str | None = None,
        chat_jid: str | None = None,
        *,
        msg_id: str | None = None,
    ) -> None:
        """Marca uno o varios mensajes como leídos (doble tick azul)."""
        await read_msg(
            self._ws,
            self._transport,
            target=target,
            sender_jid=sender_jid,
            chat_jid=chat_jid,
            debug=self.debug,
            msg_id=msg_id,
        )

    async def send_presence(self, state: str, to_jid: str | None = None) -> None:
        """Envía cualquier estado: composing, recording, paused, available, unavailable."""
        await send_presence(self._ws, self._transport, state, to_jid, self.debug)

    async def send_typing(self, to_jid: str, composing: bool = True) -> None:
        """Muestra el indicador 'escribiendo...' al destinatario."""
        await send_typing(self._ws, self._transport, to_jid, composing, self.debug)

    async def stop_typing(self, to_jid: str) -> None:
        """Oculta el indicador 'escribiendo...'."""
        await stop_typing(self._ws, self._transport, to_jid, self.debug)

    async def send_recording(self, to_jid: str, recording: bool = True) -> None:
        """Muestra el indicador 'grabando audio...' al destinatario."""
        await send_recording(self._ws, self._transport, to_jid, recording, self.debug)

    async def stop_recording(self, to_jid: str) -> None:
        """Oculta el indicador 'grabando audio...'."""
        await stop_recording(self._ws, self._transport, to_jid, self.debug)

    async def set_online(self) -> None:
        """Marca la cuenta como en línea (available)."""
        await set_online(self._ws, self._transport, self.debug)

    async def set_offline(self) -> None:
        """Marca la cuenta como desconectada (unavailable)."""
        await set_offline(self._ws, self._transport, self.debug)

    async def react_msg(
        self,
        to_jid: str,
        emoji: str,
        target: Any = None,
        *,
        target_msg_id: str | None = None,
        target_sender: str | None = None,
    ) -> str:
        """Reacciona a un mensaje con un emoji (puedes pasar target=msg o campos sueltos)."""
        return await react_msg(
            self._ws,
            self._transport,
            self.signal,
            to_jid,
            emoji,
            target=target,
            target_msg_id=target_msg_id,
            target_sender=target_sender,
            debug=self.debug,
        )

    async def send_sticker(
        self,
        to_jid: str,
        sticker: str | Path | bytes,
        *,
        reply: Any = None,
        quoted_msg_id: str | None = None,
        quoted_sender: str | None = None,
        quoted_text: str | None = None,
        tag: Any = None,
        g_tag: Any = None,
        forward: bool | int = False,
        forwarding_score: int | None = None,
        is_animated: bool = False,
    ) -> str:
        """Envía un sticker normal desde archivo local, URL (http/https) o bytes."""
        return await send_sticker(
            self._ws,
            self._transport,
            self.signal,
            self._pending_iqs,
            to_jid,
            sticker,
            quoted=reply,
            quoted_msg_id=quoted_msg_id,
            quoted_sender=quoted_sender,
            quoted_text=quoted_text,
            tag=tag,
            g_tag=g_tag,
            forward=forward,
            forwarding_score=forwarding_score,
            is_animated=is_animated,
            media_conn_cache=self._media_conn,
            debug=self.debug,
        )

    async def sticker_react(
        self,
        to_jid: str,
        target: Any,
        sticker: str | Path | bytes,
        *,
        target_msg_id: str | None = None,
        target_sender: str | None = None,
        from_me: bool | None = None,
        is_animated: bool = False,
    ) -> str:
        """Reacciona a un mensaje con un sticker (Sticker Annotation). Acepta local, URL o bytes."""
        return await sticker_react(
            self._ws,
            self._transport,
            self.signal,
            self._pending_iqs,
            to_jid,
            target,
            sticker,
            target_msg_id=target_msg_id,
            target_sender=target_sender,
            from_me=from_me,
            is_animated=is_animated,
            media_conn_cache=self._media_conn,
            debug=self.debug,
        )

    # ------------------------------------------------------------------ #
    #  Bucle de conexión                                                    #
    # ------------------------------------------------------------------ #

    async def _connect_once(self) -> bool:
        if self.pairing.is_registered:
            mode = "LOGIN"
        elif self.phone_number:
            mode = "CODE"
        else:
            mode = "QR"
        print(f"[*] Conectando a WhatsApp ({mode})...")

        should_reconnect = False
        keepalive_task: asyncio.Task | None = None
        self._pairing_code_requested = False

        self.signal = SignalSessionManager(
            ident_priv_bytes=self.pairing.ident_priv_bytes,
            ident_pub_bytes=self.pairing.ident_pub_bytes,
            skey_priv_bytes=self.pairing.skey_priv_bytes,
            prekeys=self.prekeys,
        )

        async with websockets.connect(
            WA_WS_URL,
            origin=WA_ORIGIN,
            user_agent_header=WA_USER_AGENT,
            compression=None,
            ping_interval=None,
            ping_timeout=None,
        ) as ws:
            self._ws = ws

            ephemeral_priv, _, ephemeral_pub = generate_x25519_keypair()
            noise = NoiseHandshakeState()
            noise.start(WA_HEADER)
            noise.authenticate(ephemeral_pub)

            hello = HandshakeMessage()
            hello.client_hello.ephemeral = ephemeral_pub
            await ws.send(self._build_frame(hello.SerializeToString(), include_header=True))

            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(resp, str):
                resp = resp.encode("latin-1")

            frame_len = int.from_bytes(resp[:3], "big")
            server_hello = HandshakeMessage()
            server_hello.ParseFromString(resp[3 : 3 + frame_len])
            sh = server_hello.server_hello

            noise.authenticate(sh.ephemeral)
            server_ephemeral_pub = x25519.X25519PublicKey.from_public_bytes(sh.ephemeral)
            noise.mix_key(ephemeral_priv.exchange(server_ephemeral_pub))

            server_static_bytes = noise.decrypt(sh.static)
            server_static_pub = x25519.X25519PublicKey.from_public_bytes(server_static_bytes)
            noise.mix_key(ephemeral_priv.exchange(server_static_pub))
            noise.decrypt(sh.payload)

            enc_static = noise.encrypt(self.pairing.static_pub)
            noise.mix_key(self.pairing.static_priv.exchange(server_ephemeral_pub))
            enc_payload = noise.encrypt(self.pairing.build_client_payload())

            finish_msg = HandshakeMessage()
            finish_msg.client_finish.static = enc_static
            finish_msg.client_finish.payload = enc_payload
            await ws.send(self._build_frame(finish_msg.SerializeToString(), include_header=False))

            self._transport = noise.finish()

            buffer = bytearray()

            try:
                while True:
                    chunk = await asyncio.wait_for(ws.recv(), timeout=90)
                    if isinstance(chunk, str):
                        chunk = chunk.encode("latin-1")
                    buffer.extend(chunk)

                    while len(buffer) >= 3:
                        length = int.from_bytes(buffer[:3], "big")
                        if len(buffer) < 3 + length:
                            break
                        encrypted_frame = bytes(buffer[3 : 3 + length])
                        del buffer[: 3 + length]

                        decrypted = self._transport.decrypt(encrypted_frame)
                        node = decode_binary_node(self._unpack_transport(decrypted))

                        if self.debug:
                            print(f"[OK] {node}")
                        await self._emit("node", node)

                        if node.tag == "success":
                            if keepalive_task is None:
                                keepalive_task = asyncio.create_task(
                                    keepalive_loop(ws, self._transport, self.debug)
                                )
                            await self._emit("ready", self.pairing.jid)
                            continue

                        reconnect = await handle_node(node, self)
                        if reconnect:
                            should_reconnect = True
                            return True

            except asyncio.TimeoutError:
                print("[*] Timeout esperando actividad. Reconectando...")
                should_reconnect = True
            except websockets.ConnectionClosed as e:
                print(f"[-] Conexión cerrada: {e}. Reconectando...")
                should_reconnect = True
            finally:
                if keepalive_task is not None:
                    keepalive_task.cancel()
                for fut in self._pending_iqs.values():
                    if not fut.done():
                        fut.cancel()
                self._pending_iqs.clear()
                self._ws = None
                self._transport = None

        return should_reconnect

    async def start(self):
        while True:
            try:
                should_reconnect = await self._connect_once()
                if not should_reconnect:
                    break
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
                print(f"[!] Error de conexión ({type(e).__name__}: {e}). Reintento en 3 segundos...")
                await asyncio.sleep(3)
                continue
            await asyncio.sleep(1)