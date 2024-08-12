# There is some basic functions for a whatsapp bot conection... id whould work without anothers dependencies
# This example does not use multi device whatsapp

import logging, os, signal, sys
from datetime import timedelta
from snakechat.client import NewClient
from snakechat.events import ConnectedEv, MessageEv, PairStatusEv, event
from snakechat.proto.snakechat_pb2 import JID
from snakechat.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
from snakechat.types import MessageServerID
from snakechat.utils import log
from snakechat.utils.enum import ReceiptType

sys.path.insert(0, os.getcwd())
signal.signal(signal.SIGINT, lambda *_: event.set())

log.setLevel(logging.DEBUG)

client = NewClient("db.sqlite3")

@client.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv):
    log.info("⚡ Connected - if there is some problems pleace restart the panel/cmd after made the conection socket!")
# Sometimes there is a error from "GoSnakechat" importations.
@client.event(MessageEv)
def on_message(client: NewClient, message: MessageEv):
    text = message.Message.conversation or message.Message.extendedTextMessage.text
    chat = message.Info.MessageSource.Chat
    actions = {
        "ping": lambda: client.reply_message("pong", message),
        "_test_link_preview": lambda: client.send_message(chat, "Test https://github.com/ToxiPain/snakechat", link_preview=True),
        "_sticker": lambda: client.send_sticker(chat, "https://mystickermania.com/cdn/stickers/anime/spy-family-anya-smirk-512x512.png"),
        "_image": lambda: client.send_image(chat, "https://download.samplelib.com/png/sample-boat-400x300.png", caption="Test", quoted=message),
        "viewonce": lambda: client.send_image(chat, "https://pbs.twimg.com/media/GC3ywBMb0AAAEWO?format=jpg&name=medium", viewonce=True),
        "profile_pict": lambda: client.send_message(chat, client.get_profile_picture(chat).__str__()),
        "logout": lambda: client.logout(),
    }
    if text in actions:
        actions[text]()

@client.event(PairStatusEv)
def pair_status_message(_: NewClient, message: PairStatusEv):
    log.info(f"Logged in as {message.ID.User}")

if __name__ == "__main__":
    client.connect()
