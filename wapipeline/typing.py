# wapipeline/typing.py — Todos los estados de chatstate y presencia
# Soporta: composing (escribiendo), recording (grabando audio), paused, available (online), unavailable (offline)
from binary import BinaryNode
from .handler import base_jid, is_group, send_node

_STATE_ALIASES = {
    "composing": "composing",
    "typing": "composing",
    "recording": "recording",
    "audio": "recording",
    "paused": "paused",
    "stop": "paused",
    "available": "available",
    "online": "available",
    "unavailable": "unavailable",
    "offline": "unavailable",
}


async def send_presence(
    ws,
    transport,
    state: str,
    to_jid: str | None = None,
    debug: bool = False,
) -> None:
    """
    Envía cualquier estado de presencia o chatstate de WhatsApp:
      - "composing" / "typing"    → "escribiendo..." (requiere to_jid)
      - "recording" / "audio"     → "grabando audio..." (requiere to_jid)
      - "paused" / "stop"         → detiene escribiendo/grabando (requiere to_jid)
      - "available" / "online"    → en línea (presencia global)
      - "unavailable" / "offline" → desconectado (presencia global)
    """
    normalized = _STATE_ALIASES.get(state.strip().lower())
    if not normalized:
        valid = ", ".join(sorted(set(_STATE_ALIASES.values())))
        raise ValueError(f"Estado inválido {state!r}. Usa uno de: {valid}")

    if normalized in ("available", "unavailable"):
        node = BinaryNode(tag="presence", attrs={"type": normalized})
        await send_node(ws, transport, node, debug)
        label = "EN LÍNEA" if normalized == "available" else "DESCONECTADO"
        print(f"[>>> PRESENCE] {label} ({normalized})")
        return

    if not to_jid:
        raise ValueError(f"El estado '{normalized}' requiere un to_jid.")

    target = base_jid(to_jid)
    group = is_group(target)

    if normalized == "composing":
        child = BinaryNode(tag="composing")
        estado = "ESCRIBIENDO"
    elif normalized == "recording":
        child = BinaryNode(tag="composing", attrs={"media": "audio"})
        estado = "GRABANDO AUDIO"
    else:
        child = BinaryNode(tag="paused")
        estado = "PAUSADO"

    node = BinaryNode(
        tag="chatstate",
        attrs={"to": target},
        content=[child],
    )
    await send_node(ws, transport, node, debug)
    destino = "GRUPO" if group else "CHAT"
    print(f"[>>> CHATSTATE ({destino})] {estado} → {to_jid}")


async def send_typing(
    ws,
    transport,
    to_jid: str,
    composing: bool = True,
    debug: bool = False,
) -> None:
    """Muestra u oculta el indicador 'escribiendo...' en la conversación."""
    await send_presence(ws, transport, "composing" if composing else "paused", to_jid, debug)


async def stop_typing(ws, transport, to_jid: str, debug: bool = False) -> None:
    """Atajo para cancelar el indicador de escritura."""
    await send_presence(ws, transport, "paused", to_jid, debug)


async def send_recording(
    ws,
    transport,
    to_jid: str,
    recording: bool = True,
    debug: bool = False,
) -> None:
    """Muestra u oculta el indicador 'grabando audio...' en la conversación."""
    await send_presence(ws, transport, "recording" if recording else "paused", to_jid, debug)


async def stop_recording(ws, transport, to_jid: str, debug: bool = False) -> None:
    """Atajo para cancelar el indicador de grabación de audio."""
    await send_presence(ws, transport, "paused", to_jid, debug)


async def set_online(ws, transport, debug: bool = False) -> None:
    """Marca la cuenta como en línea (available)."""
    await send_presence(ws, transport, "available", debug=debug)


async def set_offline(ws, transport, debug: bool = False) -> None:
    """Marca la cuenta como desconectada (unavailable)."""
    await send_presence(ws, transport, "unavailable", debug=debug)