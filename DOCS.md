# SnakeChat — Documentación

SnakeChat es una librería Python para conectarte a WhatsApp Web y construir bots o automatizaciones. Implementa el protocolo Noise XX, la criptografía Signal y el formato binario de WhatsApp sin depender de ninguna API no oficial de terceros.

---

## Requisitos

- Python 3.11+
- Dependencias (instalar con `pip install -e .` o según `pyproject.toml`):
  - `websockets`
  - `cryptography`
  - `protobuf`

---

## Instalación

```bash
git clone https://github.com/tu-usuario/snakechat.git
cd snakechat
pip install -e .
```

---

## Inicio rápido

Crea un archivo (por ejemplo `bot.py`) en la raíz del proyecto:

```python
import asyncio
from client import SnakeChatClient
from wapipeline import IncomingMessage

client = SnakeChatClient(debug=False)

@client.on("ready")
async def on_ready(jid: str):
    print(f"Conectado como: {jid}")

@client.on("message")
async def on_message(msg: IncomingMessage):
    if msg.text == "!hola":
        await client.send_msg(msg.chat_jid, "¡Hola! 🐍")

if __name__ == "__main__":
    asyncio.run(client.start())
```

La primera vez que ejecutes el bot, se mostrará un **QR en la terminal**. Escanéalo con WhatsApp en tu teléfono (igual que WhatsApp Web). Una vez vinculado, la sesión se guarda y no necesitas volver a escanear.

---

## Eventos

Registra handlers con el decorador `@client.on(evento)`.

| Evento      | Parámetro             | Cuándo se dispara                        |
|-------------|-----------------------|------------------------------------------|
| `"ready"`   | `jid: str`            | Conexión establecida y sesión lista      |
| `"message"` | `msg: IncomingMessage`| Llega un mensaje nuevo (texto, media, …) |

---

## IncomingMessage — campos principales

```python
msg.text          # Texto del mensaje (str o None)
msg.chat_jid      # JID del chat (grupo @g.us o usuario @s.whatsapp.net)
msg.sender        # JID completo del remitente
msg.sender_base   # JID limpio del remitente (sin device suffix)
msg.push_name     # Nombre de contacto del remitente
msg.id            # ID único del mensaje
msg.is_group      # True si el mensaje viene de un grupo
msg.quoted        # QuotedMessage si el mensaje cita otro, None si no
msg.mentions      # Lista de JIDs mencionados
msg.group_mentions# Lista de grupos mencionados
msg.is_forwarded  # True si el mensaje fue reenviado
```

---

## Funciones del cliente

Todas son `async` y deben llamarse con `await`.

### Enviar mensaje de texto

```python
await client.send_msg(chat_jid, "Hola mundo")
```

**Con reply (citar un mensaje):**
```python
await client.send_msg(chat_jid, "Te respondo", reply=msg)
```

**Con forward (etiquetar como reenviado):**
```python
await client.send_msg(chat_jid, "Mensaje reenviado", forward=True)
```

**Con mención de usuario:**
```python
from wapipeline import tag_user

await client.send_msg(chat_jid, f"Hola {tag_user(msg)}!", tag=[msg])
```

**Con mención de grupo:**
```python
from wapipeline import tag_group

group_jid = "120363428993297781@g.us"
await client.send_msg(chat_jid, f"Checa {tag_group(group_jid)}", g_tag=[(group_jid, "Mi Grupo")])
```

---

### Mencionar usuarios directamente

```python
await client.mention_user(chat_jid, users=msg, text="Oye!")
```

- `ghost=True`: menciona sin mostrar el `@` en el texto (notificación silenciosa).

```python
await client.mention_user(chat_jid, users=[msg, otro_jid], text="Hey equipo", ghost=False)
```

---

### Mencionar grupos directamente

```python
await client.mention_group(chat_jid, groups=(group_jid, "Nombre del Grupo"), text="Entra aquí!")
```

---

### Editar un mensaje

```python
msg_id = await client.send_msg(chat_jid, "Texto original")
await client.edit_msg(chat_jid, msg_id, "Texto corregido")
```

---

### Eliminar un mensaje

```python
# Eliminar el mensaje citado por el usuario
await client.delete_msg(chat_jid, msg.quoted)

# O pasar el ID directamente
await client.delete_msg(chat_jid, msg_id)
```

---

### Marcar como leído

```python
await client.read_msg(msg)
```

---

### Reaccionar con emoji

```python
await client.react_msg(chat_jid, "👍", target=msg)

# Eliminar reacción
await client.react_msg(chat_jid, "", target=msg)
```

---

### Enviar sticker

```python
await client.send_sticker(chat_jid, "ruta/al/sticker.png")
```

También acepta `.webp`. Si pasas un `.png` o `.jpg`, se convierte automáticamente.

---

### Reaccionar con sticker

```python
await client.sticker_react(chat_jid, msg, "ruta/sticker.png")
```

---

### Presencia y estado de escritura

```python
await client.set_online()
await client.set_offline()

await client.send_typing(chat_jid)     # "Escribiendo…"
await client.stop_typing(chat_jid)

await client.send_recording(chat_jid)  # "Grabando audio…"
await client.stop_recording(chat_jid)
```

---

## Helpers de normalización

Útiles si necesitas trabajar con JIDs directamente.

```python
from wapipeline import (
    tag_user,                 # "@123456789" (texto visible para mencionar)
    tag_group,                # "@120363…@g.us" (token de mención de grupo)
    normalize_mention_jids,   # lista de JIDs de usuario normalizados
    normalize_group_mentions, # lista de (jid, subject) de grupos normalizados
)
```

---

## Helpers de recepción

```python
from wapipeline import (
    extract_text,          # obtiene texto de un nodo raw
    extract_mentions,      # extrae JIDs mencionados
    extract_group_mentions,# extrae menciones de grupo
    extract_forward_info,  # (is_forwarded, forwarding_score)
    extract_quoted,        # construye QuotedMessage desde un nodo
)
```

Estos se usan internamente por `handle_node`, pero los puedes usar si procesas nodos crudos.

---

## Estructura del proyecto

```
snakechat/
├── client.py              # SnakeChatClient — punto de entrada
├── wapipeline/
│   ├── send_msg.py        # send_msg, mention_user, mention_group y todos sus helpers
│   ├── edit_msg.py        # edit_msg
│   ├── delete_msg.py      # delete_msg
│   ├── read_msg.py        # read_msg
│   ├── react_msg.py       # react_msg
│   ├── send_sticker.py    # send_sticker
│   ├── sticker_react.py   # sticker_react
│   ├── typing.py          # presencia y estado de escritura
│   ├── media.py           # carga y subida de media
│   ├── receive.py         # parseo de mensajes entrantes
│   └── handler.py         # motor: relay_message, handle_node, IncomingMessage, …
├── crypto/                # Noise XX, Signal, claves X25519
├── binary/                # Encoder/decoder binario de WhatsApp
├── protobuf/              # Protobuf compilado (WAMessage, Handshake, …)
├── state/                 # Pairing y prekeys (sesión persistente)
└── example/
    └── example.py         # Bot de ejemplo con todos los comandos
```

---

## Ejemplo completo

Mira [`example/example.py`](example/example.py) para ver un bot funcional que demuestra todos los comandos: `!msg`, `!reply`, `!forward`, `!mention`, `!mgroup`, `!edit`, `!delete`, `!read`, `!typing`, `!recording`, `!online`, `!offline`, `!react`, `!sticker`, `!sreact` e `!info`.

---

## Notas

- SnakeChat **no** es un cliente oficial de WhatsApp. Úsalo de forma responsable.
- La sesión se guarda en disco automáticamente tras el primer escaneo de QR.
- Si tu sesión caduca, simplemente ejecuta el bot de nuevo y vuelve a escanear el QR.
