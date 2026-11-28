# <p align="center">(En Desarrollo) SnakeChat WA 🐍</p> <p align="center"> <img src="src/logo.jpg" width="200px">
</p>

[![Whatsapp](https://img.shields.io/badge/Contacto-WhatsApp-%2322BC18)](https://wa.me/50557418454)
[![Support](https://img.shields.io/badge/Correo%20-Gmail-red)](mailto:allstarf123@gmail.com)
[![Version](https://img.shields.io/badge/version-1.0.0-22BC18?style=flat-square)](https://github.com/ToxiPain/Snakechat/releases)
[![Status](https://img.shields.io/badge/status-in%20development-orange?style=flat-square)](https://github.com/ToxiPain/Snakechat)
[![Updates](https://img.shields.io/badge/updates-follow%20development-blue?style=flat-square)](https://github.com/ToxiPain/Snakechat/commits/main)

SnakeChat es un proyecto de API WebSocket basado en una conexión no oficial de WhatsApp Web, diseñado principalmente para ser utilizado en Python. No requiere tokens ni claves externas para funcionar. Soporta interacciones con WhatsApp Web y es totalmente compatible con WhatsApp Multi-Devices. Al mismo tiempo, se busca que la conexión proporcione la mayoría de las funciones operativas básicas para evitar el uso de varias bibliotecas y dependencias adicionales en tu proyecto.

### Información:
* **SnakeChat no requiere el uso de Selenium u otros navegadores que afecten la velocidad de respuesta, ya que basa su funcionamiento directamente en websockets, lo que genera una interfaz de usuario funcional basado en lenguaje Python. Esto también implica que el proyecto en cuestión que utilice SnakeChat no utilizará más de 1GB de RAM en recursos para su funcionamiento estandar, támbien permitiendo el uso de JID a diferencia de alternativas como Playwright/Puppeteer sino con los métodos mencionados anteriormente.**
- - -
### Funciones:
| Compatibilidad con | Estado |
|---|:---:|
| Vinculación MultiDevice (QR/Code) | ✅ |
| Privado y grupos | ✅ |
| Enviar mensajes de texto | ✅ |
| Envío de respuesta de mensaje | ✅ |
| Etiqueta reenviado | ✅ |
| Editar mensajes | ✅ |
| Eliminar mensajes | ✅ |
| Obtener información de usuarios | ✅ |
| Reacción de mensajes | ✅ |
| Mencionar usuarios / grupos | ✅ |
| Leer mensajes (Visto) | ✅ |
| Estado: Online / Offline / Escribiendo... / Grabando... | ✅ |
| Enviar stickers | ⚠️ (Solo imagenes planas) |
| Enviar reacción con sticker | ✅ |
| Enviar archivos multimedia (imágenes, audio y documentos) | ⏭️ (Próximamente) |
| Enviar videos | ⏭️ (Próximamente) |
| Leer información de grupos | ⏭️ (Próximamente) |
| Leer eventos de grupos en tiempo real | ⏭️ (Próximamente) |
| Modificar grupos y participantes | ⏭️ (Próximamente) |
| Reportar / bloquear mensajes | ⏭️ (Próximamente) |
| Crear encuestas | ⏭️ (Próximamente) |
| Enviar botones interactivos | ⏭️ (Próximamente) |
| Enviar listas interactivas | ⏭️ (Próximamente) |
| Enviar contactos | ⏭️ (Próximamente) |
| Implementación de canales | ⏭️ (Próximamente) |
- - -
### Instalación:
**Instalación directa:**
```bash
py -m pip install "git+https://github.com/ToxiPain/Snakechat.git"
```
**Instalación vía archivo `requirements.txt`:**
```txt
snakechat @ git+https://github.com/ToxiPain/Snakechat.git
```
- - -
### Ejemplo de uso:
**Crear la instancia de `SnakeChatClient` e inicializar:**
```python
import asyncio
from client import SnakeChatClient

# Vinculación por QR (Default):
client = SnakeChatClient(debug=False)

# Vinculación por Pairing Code (8 dígitos):
# client = SnakeChatClient(debug=False, phone_number="505874182xx")

# Escuchar cuando la conexión esté lista:
@client.on("ready")
async def on_ready(jid: str):
    print(f"[+] Conectado como: {jid}")

# Ejecutar el bot (punto de entrada)
if __name__ == "__main__":
    asyncio.run(client.start())
```
**Escuchar mensajes entrantes:**
```python
from wapipeline import IncomingMessage, tag_user, tag_group

@client.on("message")
async def on_message(umsg: IncomingMessage):
    if not umsg.text:
        return

    chat_jid = umsg.chat_jid
```
**Envío de mensajes:**
```python
await client.send_msg(chat_jid, "¡Hola Mundo!")
```
**Envío de respuesta de mensaje:**
```python
await client.send_msg(chat_jid, "¡Respuesta de mensaje!", reply=umsg)
```
**Editar un mensaje:**
```python
msg_id = await client.send_msg(chat_jid, "Texto original")
await client.edit_msg(chat_jid, msg_id, "Texto editado")
```
**Eliminar un mensaje:**
```python
await client.delete_msg(chat_jid, umsg.quoted)
```
**Lectura de mensajes:**
```python
await client.read_msg(umsg)
```
**Reacción de mensajes:**
```python
await client.react_msg(chat_jid, "👍", target=umsg)
```
**Mencionar usuarios:**
```python
await client.send_msg(chat_jid, f"Hola {tag_user(umsg)}!", tag=[umsg])
```
**Mencionar grupos:**
```python
await client.send_msg(chat_jid, f"Mención de grupo {tag_group(group_jid)}", g_tag=[(group_jid, "Mi Grupo 2026")])
```
**Enviar sticker:**
```python
# Local:
await client.send_sticker(chat_jid, "ruta/al/sticker.png")
# URL:
await client.send_sticker(chat_jid, "https://ejemplo.com/imagen.png")
```
**Reaccionar con sticker:**
```python
# Local
await client.sticker_react(chat_jid, umsg, "ruta/al/sticker.png")
# URL
await client.sticker_react(chat_jid, umsg, "https://ejemplo.com/imagen.png")
```
- - -
### Disclaimer:
Este proyecto no es oficial de Whatsapp ni está afiliado ni respaldado por Meta. Todas las marcas y logotipos pertenecen a sus respectivos propietarios ([whatsapp.com](https://www.whatsapp.com/)).
SnakeChat utiliza métodos no oficiales de conexión a WhatsApp Web, cuyo uso puede provocar restricciones o bloqueos de cuenta. El uso de esta herramienta es bajo tu propia responsabilidad. Los desarrolladores no se hacen responsables de las consecuencias derivadas de su uso.
- - -
### Runea el ejemplo:
**Ver script de ejemplo:** [Example](https://github.com/ToxiPain/Snakechat/blob/main/example/example.py)
- - -
[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/toxipain)
