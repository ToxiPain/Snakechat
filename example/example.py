# Ejemplo completo: funciones de SnakeChat
# Demuestra: send_msg (texto, reply, tag, ghost, g_tag, forward), edit_msg, delete_msg, read_msg,
#            typing/recording/presence, react_msg, send_sticker, sticker_react + info
# Funciona en chat individual (@s.whatsapp.net) y grupos (@g.us)
import asyncio
import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from client import SnakeChatClient
from wapipeline import IncomingMessage, tag_user, tag_group

STICKER_PATH = os.path.join(ROOT_DIR, "src", "prueba.png")
GROUP_JID = "120363428993297781@g.us"

# Pon tu número con código de país (sin +) para vincular por Pairing Code, o None para QR:
PHONE_NUMBER = None  # Ej: "50557418454"

client = SnakeChatClient(debug=False, phone_number="526561505182")


@client.on("ready")
async def on_ready(jid: str):
    print("\n" + "=" * 60)
    print(f"[+] SnakeChat listo y conectado como: {jid}")
    print("=" * 60 + "\n")


@client.on("message")
async def on_message(umsg: IncomingMessage):
    umsg_name = umsg.push_name or umsg.sender
    chat_jid = umsg.chat_jid          # grupo (@g.us) o JID del remitente
    tipo = "[GRUPO]" if umsg.is_group else "[CHAT]"

    print(f"{tipo} {umsg_name} ({umsg.sender}): {umsg.text}")

    if not umsg.text:
        return

    cmd = umsg.text.strip().lower()

    # ── !msg ─────────────────────────────────────────────────────────────────
    if cmd == "!msg":
        await client.send_msg(chat_jid, "¡Hola Mundo desde Snakechat! 🐍")

    # ── !reply ───────────────────────────────────────────────────────────────
    elif cmd == "!reply":
        await client.send_msg(chat_jid, "¡Te estoy respondiendo con quote! 💬", reply=umsg)

    # ── !forward ─────────────────────────────────────────────────────────────
    elif cmd == "!forward":
        await client.send_msg(chat_jid, "Mensaje con etiqueta de Reenviado ↪️", forward=True)

    # ── !mention ─────────────────────────────────────────────────────────────
    elif cmd == "!mention":
        await client.send_msg(chat_jid, f"¡Hola {tag_user(umsg)} con mención! 💚", tag=[umsg])

    # ── !mgroup ──────────────────────────────────────────────────────────────
    elif cmd == "!mgroup":
        await client.send_msg(chat_jid, f"Mención de grupo {tag_group(GROUP_JID)} 💙", g_tag=[(GROUP_JID, "Grupo SnakeChat")])

    # ── !edit ────────────────────────────────────────────────────────────────
    elif cmd == "!edit":
        original = await client.send_msg(chat_jid, "Mensaje original... (3 Segundos)")
        await asyncio.sleep(3)
        await client.edit_msg(chat_jid, original, "¡Mensaje editado con éxito!")

    # ── !delete ──────────────────────────────────────────────────────────────
    elif cmd == "!delete":
        if umsg.quoted: await client.delete_msg(chat_jid, umsg.quoted)

    # ── !read ────────────────────────────────────────────────────────────────
    elif cmd == "!read":
        await client.read_msg(umsg)

    # ── !typing ──────────────────────────────────────────────────────────────
    elif cmd == "!typing":
        await client.send_typing(chat_jid)
        await asyncio.sleep(3)
        await client.stop_typing(chat_jid)

    # ── !recording ───────────────────────────────────────────────────────────
    elif cmd == "!recording":
        await client.send_recording(chat_jid)
        await asyncio.sleep(3)
        await client.stop_recording(chat_jid)

    # ── !online / !offline ───────────────────────────────────────────────────
    elif cmd == "!online":
        await client.set_online()
    elif cmd == "!offline":
        await client.set_offline()

    # ── !react ───────────────────────────────────────────────────────────────
    elif cmd == "!react":
        await client.react_msg(chat_jid, "👍", target=umsg)

    # ── !sticker ─────────────────────────────────────────────────────────────
    elif cmd == "!sticker":
        await client.send_sticker(chat_jid, STICKER_PATH)

    # ── !sreact ──────────────────────────────────────────────────────────────
    elif cmd == "!sreact":
        await client.sticker_react(chat_jid, umsg, STICKER_PATH)

    # ── !info ────────────────────────────────────────────────────────────────
    elif cmd == "!info":
        info_text = (
            "ℹ️ *Información del usuario y mensaje*\n\n"
            f"• *Nombre:* {umsg.push_name or 'No disponible'}\n"
            f"• *Sender:* {umsg.sender}\n"
            f"• *Sender base:* {umsg.sender_base}\n"
            f"• *Chat JID:* {umsg.chat_jid}\n"
            f"• *Es grupo:* {'Sí' if umsg.is_group else 'No'}\n"
            f"• *LID:* {umsg.lid or 'No disponible'}\n"
            f"• *JID (PN):* {umsg.jid or 'No disponible'}\n"
            f"• *Número:* {umsg.number or 'No disponible'}\n"
            f"• *Dispositivo:* {umsg.device or 'Principal'}\n"
            f"• *Modo:* {umsg.addressing_mode or 'No especificado'}\n"
            f"• *ID Mensaje:* {umsg.id}"
        )
        await client.send_msg(chat_jid, info_text)

    # ── !help ────────────────────────────────────────────────────────────────
    elif cmd == "!help":
        help_text = (
            "🐍 *SnakeChat – Comandos disponibles*\n\n"
            "• !msg       ➜ mensaje de prueba\n"
            "• !reply     ➜ reply citando tu mensaje\n"
            "• !forward   ➜ mensaje con etiqueta Reenviado\n"
            "• !mention   ➜ mencionarte con @\n"
            "• !mgroup    ➜ mencionar grupo por ID\n"
            "• !edit      ➜ enviar mensaje y editarlo a los 3 s\n"
            "• !delete    ➜ borrar el mensaje citado\n"
            "• !read      ➜ marcar tu mensaje como leído\n"
            "• !typing    ➜ mostrar 'escribiendo...' 3 s\n"
            "• !recording ➜ mostrar 'grabando audio...' 3 s\n"
            "• !online    ➜ marcar estado en línea\n"
            "• !offline   ➜ marcar estado desconectado\n"
            "• !react     ➜ reaccionar con 👍\n"
            "• !sticker   ➜ enviar sticker\n"
            "• !sreact    ➜ reaccionar con sticker\n"
            "• !info      ➜ mostrar datos de tu mensaje y perfil\n"
            "• !help      ➜ este menú"
        )
        await client.send_msg(chat_jid, help_text)


if __name__ == "__main__":
    asyncio.run(client.start())