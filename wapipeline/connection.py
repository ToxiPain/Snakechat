# Estado de conexión: modelos de mensaje entrante/citado y loop de keep-alive
import asyncio
from dataclasses import dataclass, field

from binary import BinaryNode
from .transport import send_node


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