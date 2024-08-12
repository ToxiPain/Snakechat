#Example with new characteristics to test it... If some module does not work advice me at +505 57418454 pleace!. 
# Buttons modules are in Beta Test because we put it from "Whatsapp Bussiness OFC Api"
# This example use MultiDevice Whatsapp.

import logging, os, signal, sys
from datetime import timedelta
from snakechat.client import ClientFactory, NewClient
from snakechat.events import ConnectedEv, MessageEv, PairStatusEv, event, ReceiptEv, CallOfferEv
from snakechat.proto.waE2E.WAWebProtobufsE2E_pb2 import Message, FutureProofMessage, InteractiveMessage, MessageContextInfo, DeviceListMetadata
from snakechat.types import MessageServerID
from snakechat.utils import log
from snakechat.utils.enum import ReceiptType

sys.path.insert(0, os.getcwd())
signal.signal(signal.SIGINT, lambda *_: event.set())

log.setLevel(logging.DEBUG)

client_factory = ClientFactory("db.sqlite3")
for device in client_factory.get_all_devices():
    client_factory.new_client(device.JID)

@client_factory.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv):
    log.info("⚡ Connected")

@client_factory.event(ReceiptEv)
def on_receipt(_: NewClient, receipt: ReceiptEv):
    log.debug(receipt)

@client_factory.event(CallOfferEv)
def on_call(_: NewClient, call: CallOfferEv):
    log.debug(call)

@client_factory.event(MessageEv)
def on_message(client: NewClient, message: MessageEv):
    handler(client, message)

def handler(client: NewClient, message: MessageEv):
    chat = message.Info.MessageSource.Chat
    actions = {
        "ping": lambda: client.reply_message("pong", message),
        "_test_link_preview": lambda: client.send_message(chat, "Test https://github.com/ToxiPain/snakechat", link_preview=True),
        "_sticker": lambda: client.send_sticker(chat, "https://mystickermania.com/cdn/stickers/anime/spy-family-anya-smirk-512x512.png"),
        "_sticker_exif": lambda: client.send_sticker(chat, "https://mystickermania.com/cdn/stickers/anime/spy-family-anya-smirk-512x512.png", name="@snakechat", packname="2024"),
        "_image": lambda: client.send_image(chat, "https://download.samplelib.com/png/sample-boat-400x300.png", caption="Test", quoted=message),
        "_video": lambda: client.send_video(chat, "https://download.samplelib.com/mp4/sample-5s.mp4", caption="Test", quoted=message),
        "_audio": lambda: client.send_audio(chat, "https://download.samplelib.com/mp3/sample-12s.mp3", quoted=message),
        "_ptt": lambda: client.send_audio(chat, "https://download.samplelib.com/mp3/sample-12s.mp3", ptt=True, quoted=message),
        "_doc": lambda: client.send_document(chat, "https://download.samplelib.com/xls/sample-heavy-1.xls", caption="Test", filename="test.xls", quoted=message),
        "debug": lambda: client.send_message(chat, message.__str__()),
        "viewonce": lambda: client.send_image(chat, "https://pbs.twimg.com/media/GC3ywBMb0AAAEWO?format=jpg&name=medium", viewonce=True),
        "profile_pict": lambda: client.send_message(chat, client.get_profile_picture(chat).__str__()),
        "status_privacy": lambda: client.send_message(chat, client.get_status_privacy().__str__()),
        "read": lambda: client.send_message(chat, client.mark_read(message.Info.ID, chat=chat, sender=message.Info.MessageSource.Sender, receipt=ReceiptType.READ).__str__()),
        "read_channel": lambda: handle_channel_interaction(client, chat),
        "logout": lambda: client.logout(),
        "send_react_channel": lambda: handle_react_channel(client, chat),
        "subscribe_channel_updates": lambda: handle_subscribe_channel(client, chat),
        "mute_channel": lambda: handle_mute_channel(client, chat),
        "set_diseapearing": lambda: client.send_message(chat, client.set_default_disappearing_timer(timedelta(days=7)).__str__()),
        "test_contacts": lambda: client.send_message(chat, client.contact.get_all_contacts().__str__()),
        "build_sticker": lambda: client.send_message(chat, client.build_sticker_message("https://mystickermania.com/cdn/stickers/anime/spy-family-anya-smirk-512x512.png", message, "2024", "snakechat")),
        "build_video": lambda: client.send_message(chat, client.build_video_message("https://download.samplelib.com/mp4/sample-5s.mp4", "Test", message)),
        "build_image": lambda: client.send_message(chat, client.build_image_message("https://download.samplelib.com/png/sample-boat-400x300.png", "Test", message)),
        "build_document": lambda: client.send_message(chat, client.build_document_message("https://download.samplelib.com/xls/sample-heavy-1.xls", "Test", "title", "sample-heavy-1.xls", quoted=message)),
        "put_muted_until": lambda: client.chat_settings.put_muted_until(chat, timedelta(seconds=5)),
        "put_pinned_enable": lambda: client.chat_settings.put_pinned(chat, True),
        "put_pinned_disable": lambda: client.chat_settings.put_pinned(chat, False),
        "put_archived_enable": lambda: client.chat_settings.put_archived(chat, True),
        "put_archived_disable": lambda: client.chat_settings.put_archived(chat, False),
        "get_chat_settings": lambda: client.send_message(chat, client.chat_settings.get_chat_settings(chat).__str__()),
        "button": lambda: send_button(client, message)
    }
    if text := message.Message.conversation or message.Message.extendedTextMessage.text:
        actions.get(text, lambda: None)()

def handle_channel_interaction(client, chat):
    metadata = client.get_newsletter_info_with_invite("https://whatsapp.com/channel/0029Va4K0PZ5a245NkngBA2M")
    err = client.follow_newsletter(metadata.ID)
    client.send_message(chat, "error: " + err.__str__())
    resp = client.newsletter_mark_viewed(metadata.ID, [MessageServerID(0)])
    client.send_message(chat, resp.__str__() + "\n" + metadata.__str__())

def handle_react_channel(client, chat):
    metadata = client.get_newsletter_info_with_invite("https://whatsapp.com/channel/0029Va4K0PZ5a245NkngBA2M")
    data_msg = client.get_newsletter_messages(metadata.ID, 2, MessageServerID(0))
    client.send_message(chat, data_msg.__str__())
    for _ in data_msg:
        client.newsletter_send_reaction(metadata.ID, MessageServerID(0), "🗿", "")

def handle_subscribe_channel(client, chat):
    metadata = client.get_newsletter_info_with_invite("https://whatsapp.com/channel/0029Va4K0PZ5a245NkngBA2M")
    result = client.newsletter_subscribe_live_updates(metadata.ID)
    client.send_message(chat, result.__str__())

def handle_mute_channel(client, chat):
    metadata = client.get_newsletter_info_with_invite("https://whatsapp.com/channel/0029Va4K0PZ5a245NkngBA2M")
    client.send_message(chat, client.newsletter_toggle_mute(metadata.ID, False).__str__())

def send_button(client, message):
    chat = message.Info.MessageSource.Chat
    client.send_message(chat, Message(viewOnceMessage=FutureProofMessage(message=Message(messageContextInfo=MessageContextInfo(deviceListMetadata=DeviceListMetadata(), deviceListMetadataVersion=2), interactiveMessage=InteractiveMessage(body=InteractiveMessage.Body(text="Body Message"), footer=InteractiveMessage.Footer(text="@ToxiPain"), header=InteractiveMessage.Header(title="Title Message", subtitle="Subtitle Message", hasMediaAttachment=False), nativeFlowMessage=InteractiveMessage.NativeFlowMessage(buttons=[InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="single_select", buttonParamsJSON='{"title":"List Buttons","sections":[{"title":"title","highlight_label":"label","rows":[{"header":"header","title":"title","description":"description","id":"select 1"},{"header":"header","title":"title","description":"description","id":"select 2"}]}]}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="quick_reply", buttonParamsJSON='{"display_text":"Quick URL","url":"https://www.google.com","merchant_url":"https://www.google.com"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="cta_call", buttonParamsJSON='{"display_text":"Quick Call","id":"message"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="cta_copy", buttonParamsJSON='{"display_text":"Quick Copy","id":"123456789","copy_code":"message"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="cta_remainder", buttonParamsJSON='{"display_text":"Reminder","id":"message"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="cta_cancel_remainder", buttonParamsJSON='{"display_text":"Cancel Reminder","id":"message"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="address_message", buttonParamsJSON='{"display_text":"Address","id":"message"}'), InteractiveMessage.NativeFlowMessage.NativeFlowButton(name="send_location", buttonParamsJSON="")])))))

@client_factory.event(PairStatusEv)
def PairStatusMessage(_: NewClient, message: PairStatusEv):
    log.info(f"logged as {message.ID.User}")

if __name__ == "__main__":
    clientAquí tienes la continuación del código simplificado:

```python
    client_factory.run()
