from __future__ import annotations

import ctypes
import datetime
import re
import struct
import time
from types import NoneType
import typing
from datetime import timedelta
from io import BytesIO
from typing import Any, Optional, List, Sequence, overload

import magic
from PIL import Image
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer
from linkpreview import link_preview
from threading import Thread

from .utils.calc import AspectRatioMethod, auto_sticker


from ._binder import gocode, func_string, func_callback_bytes, func
from .builder import build_edit, build_revoke
from .events import Event, EventsManager
from .exc import (
    ContactStoreError,
    DownloadError,
    GetChatSettingsError,
    PutArchivedError,
    PutMutedUntilError,
    PutPinnedError,
    ResolveContactQRLinkError,
    SendAppStateError,
    SetDefaultDisappearingTimerError,
    SetDisappearingTimerError,
    SetGroupAnnounceError,
    SetGroupLockedError,
    SetGroupTopicError,
    SetPassiveError,
    SetPrivacySettingError,
    SetStatusMessageError,
    SubscribePresenceError,
    UnfollowNewsletterError,
    UnlinkGroupError,
    UpdateBlocklistError,
    UpdateGroupParticipantsError,
    UploadError,
    InviteLinkError,
    GetGroupInfoError,
    SetGroupPhotoError,
    GetGroupInviteLinkError,
    CreateGroupError,
    IsOnWhatsAppError,
    GetUserInfoError,
    SendMessageError,
    BuildPollVoteError,
    CreateNewsletterError,
    FollowNewsletterError,
    GetBlocklistError,
    GetProfilePictureError,
    GetStatusPrivacyError,
    GetSubGroupsError,
    GetSubscribedNewslettersError,
    LogoutError,
    MarkReadError,
    NewsletterMarkViewedError,
    NewsletterSendReactionError,
)
from .exc import (
    GetContactQrLinkError,
    GetGroupRequestParticipantsError,
    GetJoinedGroupsError,
    GetLinkedGroupParticipantsError,
    GetNewsletterInfoError,
    GetNewsletterInfoWithInviteError,
    GetNewsletterMessageUpdateError,
    GetNewsletterMessagesError,
    GetUserDevicesError,
    JoinGroupWithInviteError,
    LinkGroupError,
    NewsletterSubscribeLiveUpdatesError,
    NewsletterToggleMuteError,
)
from .proto import snakechat_pb2 as snakechat_proto
from .proto.snakechat_pb2 import (
    Contact,
    ContactEntry,
    ContactEntryArray,
    ContactInfo,
    ContactsGetContactReturnFunction,
    ContactsPutPushNameReturnFunction,
    GroupParticipant,
    Blocklist,
    GroupLinkTarget,
    MessageInfo,
    JID,
    NewsletterMessage,
    NewsletterMetadata,
    PrivacySettings,
    ProfilePictureInfo,
    StatusPrivacy,
    UploadReturnFunction,
    GroupInfo,
    JoinGroupWithLinkReturnFunction,
    GetGroupInviteLinkReturnFunction,
    GetGroupInfoReturnFunction,
    DownloadReturnFunction,
    SendMessageReturnFunction,
    UploadResponse,
    SetGroupPhotoReturnFunction,
    ReqCreateGroup,
    GroupLinkedParent,
    GroupParent,
    IsOnWhatsAppReturnFunction,
    IsOnWhatsAppResponse,
    JIDArray,
    GetUserInfoReturnFunction,
    GetUserInfoSingleReturnFunction,
    SendResponse,
    Device,
    ReturnFunctionWithError,
    LocalChatSettings,
)
from .proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps
from .proto.waE2E.WAWebProtobufsE2E_pb2 import (
    Message,
    StickerMessage,
    ContextInfo,
    ExtendedTextMessage,
    VideoMessage,
    ImageMessage,
    AudioMessage,
    DocumentMessage,
    ContactMessage,
)
from .types import MessageServerID, MessageWithContextInfo
from .utils import add_exif, gen_vcard, log, validate_link
from .utils.enum import (
    BlocklistAction,
    MediaType,
    ChatPresence,
    ChatPresenceMedia,
    LogLevel,
    ParticipantChange,
    ReceiptType,
    ClientType,
    ClientName,
    PrivacySetting,
    PrivacySettingType,
)
from .utils.ffmpeg import FFmpeg, ImageFormat
from .utils.iofile import get_bytes_from_name_or_url
from .utils.jid import Jid2String, JIDToNonAD, build_jid


class ContactStore:
    def __init__(self, uuid: bytes) -> None:
        self.uuid = uuid
        self.__client = gocode

    def put_pushname(
        self, user: JID, pushname: str
    ) -> ContactsPutPushNameReturnFunction:
        user_bytes = user.SerializeToString()
        model = ContactsPutPushNameReturnFunction.FromString(
            self.__client.PutPushName(
                user_bytes, len(user_bytes), pushname.encode()
            ).get_bytes()
        )
        if model.Error:
            raise ContactStoreError(model.Error)
        return model

    def put_contact_name(self, user: JID, fullname: str, firstname: str):
        user_bytes = user.SerializeToString()
        err = self.__client.PutContactName(
            self.uuid,
            user_bytes,
            len(user_bytes),
            fullname.encode(),
            firstname.encode(),
        ).decode()
        if err:
            return ContactStoreError(err)

    def put_all_contact_name(self, contact_entry: List[ContactEntry]):
        entry = ContactEntryArray(ContactEntry=contact_entry).SerializeToString()
        err = self.__client.PutAllContactNames(self.uuid, entry, len(entry)).decode()
        if err:
            raise ContactStoreError(err)

    def get_contact(self, user: JID) -> ContactInfo:
        jid = user.SerializeToString()
        model = ContactsGetContactReturnFunction.FromString(
            self.__client.GetContact(self.uuid, jid, len(jid)).get_bytes()
        )
        if model.Error:
            raise ContactStoreError(model.Error)
        return model.ContactInfo

    def get_all_contacts(self) -> RepeatedCompositeFieldContainer[Contact]:
        model = snakechat_proto.ContactsGetAllContactsReturnFunction.FromString(
            self.__client.GetAllContacts(self.uuid).get_bytes()
        )
        if model.Error:
            raise ContactStoreError(model.Error)
        return model.Contact


class ChatSettingsStore:
    def __init__(self, uuid: bytes) -> None:
        self.uuid = uuid
        self.__client = gocode

    def put_muted_until(self, user: JID, until: timedelta):
        user_buf = user.SerializeToString()
        return_ = self.__client.PutMutedUntil(
            self.uuid, user_buf, len(user_buf), until.total_seconds()
        )
        if return_:
            raise PutMutedUntilError(return_.decode())

    def put_pinned(self, user: JID, pinned: bool):
        user_buf = user.SerializeToString()
        return_ = self.__client.PutPinned(self.uuid, user_buf, len(user_buf), pinned)
        if return_:
            raise PutPinnedError(return_.decode())

    def put_archived(self, user: JID, archived: bool):
        user_buf = user.SerializeToString()
        return_ = self.__client.PutArchived(
            self.uuid, user_buf, len(user_buf), archived
        )
        if return_:
            raise PutArchivedError(return_.decode())

    def get_chat_settings(self, user: JID) -> LocalChatSettings:
        user_buf = user.SerializeToString()
        return_ = ReturnFunctionWithError.FromString(
            self.__client.GetChatSettings(
                self.uuid, user_buf, len(user_buf)
            ).get_bytes()
        )
        if return_.Error:
            raise GetChatSettingsError(return_.Error)
        return return_.LocalChatSettings


class NewClient:
    def __init__(
        self,
        name: str,
        jid: Optional[JID] = None,
        props: Optional[DeviceProps] = None,
        uuid: Optional[str] = None,
    ):
        self.name = name
        self.device_props = props
        self.jid = jid
        self.uuid = ((jid.User if jid else None) or uuid or name).encode()
        self.__client = gocode
        self.event = Event(self)
        self.blocking = self.event.blocking
        self.qr = self.event.qr
        self.contact = ContactStore(self.uuid)
        self.chat_settings = ChatSettingsStore(self.uuid)
        log.debug("Creando una nueva sesión para el cliente 🐍")

    def __onLoginStatus(self, s: str):
        print(s)

    def __onQr(self, qr_protoaddr: int):
        self.event._qr(self, ctypes.string_at(qr_protoaddr))

    def _parse_mention(self, text: Optional[str] = None) -> list[str]:
        if text is None:
            return []
        return [
            jid.group(1) + "@s.whatsapp.net"
            for jid in re.finditer(r"@([0-9]{5,16}|0)", text)
        ]

    def _generate_link_preview(self, text: str) -> ExtendedTextMessage | None:
        youtube_url_pattern = re.compile(
            r"(?:https?:)?//(?:www\.)?(?:youtube\.com/(?:[^/\n\s]+"
            r"/\S+/|(?:v|e(?:mbed)?)/|\S*?[?&]v=)|youtu\.be/)([a-zA-Z0-9_-]{11})",
            re.IGNORECASE,
        )
        links = re.findall(r"https?://\S+", text)
        valid_links = list(filter(validate_link, links))
        if valid_links:
            preview = link_preview(valid_links[0])
            preview_type = (
                ExtendedTextMessage.PreviewType.VIDEO
                if re.match(youtube_url_pattern, valid_links[0])
                else ExtendedTextMessage.PreviewType.NONE
            )
            msg = ExtendedTextMessage(
                title=str(preview.title),
                description=str(preview.description),
                matchedText=valid_links[0],
                canonicalURL=str(preview.link.url),
                previewType=preview_type,
            )
            if preview.absolute_image:
                thumbnail = get_bytes_from_name_or_url(str(preview.absolute_image))
                mimetype = magic.from_buffer(thumbnail, mime=True)
                if "jpeg" in mimetype or "png" in mimetype:
                    image = Image.open(BytesIO(thumbnail))
                    upload = self.upload(thumbnail, MediaType.MediaLinkThumbnail)
                    msg.MergeFrom(
                        ExtendedTextMessage(
                            JPEGThumbnail=thumbnail,
                            thumbnailDirectPath=upload.DirectPath,
                            thumbnailSHA256=upload.FileSHA256,
                            thumbnailEncSHA256=upload.FileEncSHA256,
                            mediaKey=upload.MediaKey,
                            mediaKeyTimestamp=int(time.time()),
                            thumbnailWidth=image.size[0],
                            thumbnailHeight=image.size[1],
                        )
                    )
            return msg
        return None

    def _make_quoted_message(
        self, message: snakechat_proto.Message, reply_privately: bool = False
    ) -> ContextInfo:
        return ContextInfo(
            stanzaID=message.Info.ID,
            participant=Jid2String(JIDToNonAD(message.Info.MessageSource.Sender)),
            quotedMessage=message.Message,
            remoteJID=Jid2String(JIDToNonAD(message.Info.MessageSource.Chat))
            if reply_privately
            else None,
        )

    def send_message(
        self, to: JID, message: typing.Union[Message, str], link_preview: bool = False
    ) -> SendResponse:
        to_bytes = to.SerializeToString()
        if isinstance(message, str):
            mentioned_jid = self._parse_mention(message)
            partial_msg = ExtendedTextMessage(
                text=message, contextInfo=ContextInfo(mentionedJID=mentioned_jid)
            )
            if link_preview:
                preview = self._generate_link_preview(message)
                if preview:
                    partial_msg.MergeFrom(preview)
            if partial_msg.previewType is None and not mentioned_jid:
                msg = Message(conversation=message)
            else:
                msg = Message(extendedTextMessage=partial_msg)
        else:
            msg = message
        message_bytes = msg.SerializeToString()
        sendresponse = self.__client.SendMessage(
            self.uuid, to_bytes, len(to_bytes), message_bytes, len(message_bytes)
        ).get_bytes()
        model = SendMessageReturnFunction.FromString(sendresponse)
        if model.Error:
            raise SendMessageError(model.Error)
        return model.SendResponse

    def build_reply_message(
        self,
        message: typing.Union[str, MessageWithContextInfo],
        quoted: snakechat_proto.Message,
        link_preview: bool = False,
        reply_privately: bool = False,
    ) -> Message:
        build_message = Message()
        if isinstance(message, str):
            partial_message = ExtendedTextMessage(
                text=message,
                contextInfo=ContextInfo(mentionedJID=self._parse_mention(message)),
            )
            if link_preview:
                preview = self._generate_link_preview(message)
                if preview is not None:
                    partial_message.MergeFrom(preview)
        else:
            partial_message = message
        field_name = (
            partial_message.__class__.__name__[0].lower()
            + partial_message.__class__.__name__[1:]
        )  # type: ignore
        partial_message.contextInfo.MergeFrom(
            self._make_quoted_message(quoted, reply_privately)
        )
        getattr(build_message, field_name).MergeFrom(partial_message)
        return build_message

    def reply_message(
        self,
        message: typing.Union[str, MessageWithContextInfo],
        quoted: snakechat_proto.Message,
        to: Optional[JID] = None,
        link_preview: bool = False,
        reply_privately: bool = False,
    ) -> SendResponse:
        if to is None:
            if reply_privately:
                to = JIDToNonAD(quoted.Info.MessageSource.Sender)
            else:
                to = quoted.Info.MessageSource.Chat
        return self.send_message(
            to,
            self.build_reply_message(
                message=message,
                quoted=quoted,
                link_preview=link_preview,
                reply_privately=reply_privately,
            ),
            link_preview,
        )

    def edit_message(
        self, chat: JID, message_id: str, new_message: Message
    ) -> SendResponse:
        return self.send_message(chat, build_edit(chat, message_id, new_message))

    def revoke_message(self, chat: JID, sender: JID, message_id: str) -> SendResponse:
        return self.send_message(chat, self.build_revoke(chat, sender, message_id))

    def build_poll_vote_creation(
        self, name: str, options: List[str], selectable_count: int
    ) -> Message:
        options_buf = snakechat_proto.ArrayString(data=options).SerializeToString()
        return Message.FromString(
            self.__client.BuildPollVoteCreation(
                self.uuid,
                name.encode(),
                options_buf,
                len(options_buf),
                selectable_count,
            ).get_bytes()
        )

    def build_poll_vote(
        self, poll_info: MessageInfo, option_names: List[str]
    ) -> Message:
        option_names_proto = snakechat_proto.ArrayString(
            data=option_names
        ).SerializeToString()
        poll_info_proto = poll_info.SerializeToString()
        resp = self.__client.BuildPollVote(
            self.uuid,
            poll_info_proto,
            len(poll_info_proto),
            option_names_proto,
            len(option_names_proto),
        ).get_bytes()
        model = snakechat_proto.BuildPollVoteReturnFunction.FromString(resp)
        if model.Error:
            raise BuildPollVoteError(model.Error)
        return model.PollVote

    def build_reaction(
        self, chat: JID, sender: JID, message_id: str, reaction: str
    ) -> Message:
        sender_proto = sender.SerializeToString()
        chat_proto = chat.SerializeToString()
        return Message.FromString(
            self.__client.BuildReaction(
                self.uuid,
                chat_proto,
                len(chat_proto),
                sender_proto,
                len(sender_proto),
                message_id.encode(),
                reaction.encode(),
            ).get_bytes()
        )

    def build_revoke(
        self, chat: JID, sender: JID, message_id: str, with_go: bool = False
    ) -> Message:
        if with_go:
            chat_buf = chat.SerializeToString()
            sender_buf = sender.SerializeToString()
            return Message.FromString(
                self.__client.BuildRevoke(
                    self.uuid,
                    chat_buf,
                    len(chat_buf),
                    sender_buf,
                    len(sender_buf),
                    message_id.encode(),
                ).get_bytes()
            )
        else:
            return build_revoke(chat, sender, message_id, self.get_me().JID)

    def build_sticker_message(
        self,
        file: typing.Union[str, bytes],
        quoted: Optional[snakechat_proto.Message] = None,
        name: str = "",
        packname: str = "",
    ) -> Message:
        sticker = get_bytes_from_name_or_url(file)
        animated = False
        mime = magic.from_buffer(sticker).split("/")
        if mime[0] == "image":
            io_save = BytesIO(sticker)
            stk = auto_sticker(io_save)
            stk.save(
                io_save,
                format="webp",
                exif=add_exif(name, packname),
                save_all=True,
                loop=0,
            )
            io_save.seek(0)
        else:
            with FFmpeg(sticker) as ffmpeg:
                animated = True
                sticker = ffmpeg.cv_to_webp()
                io_save = BytesIO(sticker)
                img = Image.open(io_save)
                io_save.seek(0)
                img.save(
                    io_save, format="webp", exif=add_exif(name, packname), save_all=True
                )
        upload = self.upload(io_save.getvalue())
        message = Message(
            stickerMessage=StickerMessage(
                URL=upload.url,
                directPath=upload.DirectPath,
                fileEncSHA256=upload.FileEncSHA256,
                fileLength=upload.FileLength,
                fileSHA256=upload.FileSHA256,
                mediaKey=upload.MediaKey,
                mimetype=magic.from_buffer(io_save.getvalue(), mime=True),
                isAnimated=animated,
            )
        )
        if quoted:
            message.stickerMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return message

    def send_sticker(
        self,
        to: JID,
        file: typing.Union[str, bytes],
        quoted: Optional[snakechat_proto.Message] = None,
        name: str = "",
        packname: str = "",
    ) -> SendResponse:
        return self.send_message(
            to,
            self.build_sticker_message(file, quoted, name, packname),
        )

    def build_video_message(
        self,
        file: str | bytes,
        caption: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
        viewonce: bool = False,
    ) -> Message:
        io = BytesIO(get_bytes_from_name_or_url(file))
        io.seek(0)
        buff = io.read()
        with FFmpeg(file) as ffmpeg:
            duration = int(ffmpeg.extract_info().format.duration)
            thumbnail = ffmpeg.extract_thumbnail()
        upload = self.upload(buff)
        message = Message(
            videoMessage=VideoMessage(
                URL=upload.url,
                caption=caption,
                seconds=duration,
                directPath=upload.DirectPath,
                fileEncSHA256=upload.FileEncSHA256,
                fileLength=upload.FileLength,
                fileSHA256=upload.FileSHA256,
                mediaKey=upload.MediaKey,
                mimetype=magic.from_buffer(buff, mime=True),
                JPEGThumbnail=thumbnail,
                thumbnailDirectPath=upload.DirectPath,
                thumbnailEncSHA256=upload.FileEncSHA256,
                thumbnailSHA256=upload.FileSHA256,
                viewOnce=viewonce,
                contextInfo=ContextInfo(
                    mentionedJID=self._parse_mention(caption),
                ),
            )
        )
        if quoted:
            message.videoMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return message

    def send_video(
        self,
        to: JID,
        file: str | bytes,
        caption: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
        viewonce: bool = False,
    ) -> SendResponse:
        return self.send_message(
            to, self.build_video_message(file, caption, quoted, viewonce)
        )

    def build_image_message(
        self,
        file: str | bytes,
        caption: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
        viewonce: bool = False,
    ) -> Message:
        n_file = get_bytes_from_name_or_url(file)
        img = Image.open(BytesIO(n_file))
        img.thumbnail(AspectRatioMethod(*img.size, res=200))
        thumbnail = BytesIO()
        img_saveable = img if img.mode == "RGB" else img.convert("RGB")
        img_saveable.save(thumbnail, format="jpeg")
        upload = self.upload(n_file)
        message = Message(
            imageMessage=ImageMessage(
                URL=upload.url,
                caption=caption,
                directPath=upload.DirectPath,
                fileEncSHA256=upload.FileEncSHA256,
                fileLength=upload.FileLength,
                fileSHA256=upload.FileSHA256,
                mediaKey=upload.MediaKey,
                mimetype=magic.from_buffer(n_file, mime=True),
                JPEGThumbnail=thumbnail.getvalue(),
                thumbnailDirectPath=upload.DirectPath,
                thumbnailEncSHA256=upload.FileEncSHA256,
                thumbnailSHA256=upload.FileSHA256,
                viewOnce=viewonce,
                contextInfo=ContextInfo(
                    mentionedJID=self._parse_mention(caption),
                ),
            )
        )
        if quoted:
            message.imageMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return message

    def send_image(
        self,
        to: JID,
        file: str | bytes,
        caption: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
        viewonce: bool = False,
    ) -> SendResponse:
        return self.send_message(
            to, self.build_image_message(file, caption, quoted, viewonce=viewonce)
        )

    def build_audio_message(
        self,
        file: str | bytes,
        ptt: bool = False,
        quoted: Optional[snakechat_proto.Message] = None,
    ) -> Message:
        io = BytesIO(get_bytes_from_name_or_url(file))
        io.seek(0)
        buff = io.read()
        upload = self.upload(buff)
        with FFmpeg(io.getvalue()) as ffmpeg:
            duration = int(ffmpeg.extract_info().format.duration)
        message = Message(
            audioMessage=AudioMessage(
                URL=upload.url,
                seconds=duration,
                directPath=upload.DirectPath,
                fileEncSHA256=upload.FileEncSHA256,
                fileLength=upload.FileLength,
                fileSHA256=upload.FileSHA256,
                mediaKey=upload.MediaKey,
                mimetype=magic.from_buffer(buff, mime=True),
                PTT=ptt,
            )
        )
        if quoted:
            message.audioMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return message

    def send_audio(
        self,
        to: JID,
        file: str | bytes,
        ptt: bool = False,
        quoted: Optional[snakechat_proto.Message] = None,
    ) -> SendResponse:

        return self.send_message(to, self.build_audio_message(file, ptt, quoted))

    def build_document_message(
        self,
        file: str | bytes,
        caption: Optional[str] = None,
        title: Optional[str] = None,
        filename: Optional[str] = None,
        mimetype: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
    ):
        io = BytesIO(get_bytes_from_name_or_url(file))
        io.seek(0)
        buff = io.read()
        upload = self.upload(buff)
        message = Message(
            documentMessage=DocumentMessage(
                URL=upload.url,
                caption=caption,
                directPath=upload.DirectPath,
                fileEncSHA256=upload.FileEncSHA256,
                fileLength=upload.FileLength,
                fileSHA256=upload.FileSHA256,
                mediaKey=upload.MediaKey,
                mimetype=mimetype or magic.from_buffer(buff, mime=True),
                title=title,
                fileName=filename,
                contextInfo=ContextInfo(
                    mentionedJID=self._parse_mention(caption),
                ),
            )
        )
        if quoted:
            message.documentMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return message

    def send_document(
        self,
        to: JID,
        file: str | bytes,
        caption: Optional[str] = None,
        title: Optional[str] = None,
        filename: Optional[str] = None,
        mimetype: Optional[str] = None,
        quoted: Optional[snakechat_proto.Message] = None,
    ) -> SendResponse:
        return self.send_message(
            to,
            self.build_document_message(
                file, caption, title, filename, mimetype, quoted
            ),
        )

    def send_contact(
        self,
        to: JID,
        contact_name: str,
        contact_number: str,
        quoted: Optional[snakechat_proto.Message] = None,
    ) -> SendResponse:
        message = Message(
            contactMessage=ContactMessage(
                displayName=contact_name,
                vcard=gen_vcard(contact_name, contact_number),
            )
        )
        if quoted:
            message.contactMessage.contextInfo.MergeFrom(
                self._make_quoted_message(quoted)
            )
        return self.send_message(to, message)

    def upload(
        self, binary: bytes, media_type: Optional[MediaType] = None
    ) -> UploadResponse:
        if not media_type:
            mime = MediaType.from_magic(binary)
        else:
            mime = media_type
        response = self.__client.Upload(self.uuid, binary, len(binary), mime.value)
        upload_model = UploadReturnFunction.FromString(response.get_bytes())
        if upload_model.Error:
            raise UploadError(upload_model.Error)
        return upload_model.UploadResponse

    @overload
    def download_any(self, message: Message) -> bytes: ...

    @overload
    def download_any(self, message: Message, path: str) -> NoneType: ...

    def download_any(
        self, message: Message, path: Optional[str] = None
    ) -> typing.Union[None, bytes]:
        msg_protobuf = message.SerializeToString()
        media_buff = self.__client.DownloadAny(
            self.uuid, msg_protobuf, len(msg_protobuf)
        ).get_bytes()
        media = DownloadReturnFunction.FromString(media_buff)
        if media.Error:
            raise DownloadError(media.Error)
        if path:
            with open(path, "wb") as file:
                file.write(media.Binary)
        else:
            return media.Binary
        return None

    def download_media_with_path(
        self,
        direct_path: str,
        enc_file_hash: bytes,
        file_hash: bytes,
        media_key: bytes,
        file_length: int,
        media_type: MediaType,
        mms_type: str,
    ) -> bytes:
        model = snakechat_proto.DownloadReturnFunction.FromString(
            self.__client.DownloadMediaWithPath(
                self.uuid,
                direct_path.encode(),
                enc_file_hash,
                len(enc_file_hash),
                file_hash,
                len(file_hash),
                media_key,
                len(media_key),
                file_length,
                media_type.value,
                mms_type.encode(),
            ).get_bytes()
        )
        if model.Error:
            raise DownloadError(model.Error)
        return model.Binary

    def generate_message_id(self) -> str:
        return self.__client.GenerateMessageID(self.uuid).decode()

    def send_chat_presence(
        self, jid: JID, state: ChatPresence, media: ChatPresenceMedia
    ) -> str:
        jidbyte = jid.SerializeToString()
        return self.__client.SendChatPresence(
            self.uuid, jidbyte, len(jidbyte), state.value, media.value
        ).decode()

    def is_on_whatsapp(self, *numbers: str) -> Sequence[IsOnWhatsAppResponse]:
        if numbers:
            numbers_buf = " ".join(numbers).encode()
            response = self.__client.IsOnWhatsApp(
                self.uuid, numbers_buf, len(numbers_buf)
            ).get_bytes()
            model = IsOnWhatsAppReturnFunction.FromString(response)
            if model.Error:
                raise IsOnWhatsAppError(model.Error)
            return model.IsOnWhatsAppResponse
        return []

    @property
    def is_connected(self) -> bool:
        return self.__client.IsConnected(self.uuid)

    @property
    def is_logged_in(self) -> bool:
        return self.__client.IsLoggedIn(self.uuid)

    def get_user_info(
        self, *jid: JID
    ) -> RepeatedCompositeFieldContainer[GetUserInfoSingleReturnFunction]:
        jidbuf = JIDArray(JIDS=jid).SerializeToString()
        getUser = self.__client.GetUserInfo(self.uuid, jidbuf, len(jidbuf)).get_bytes()
        model = GetUserInfoReturnFunction.FromString(getUser)
        if model.Error:
            raise GetUserInfoError(model.Error)
        return model.UsersInfo

    def get_group_info(self, jid: JID) -> GroupInfo:
        jidbuf = jid.SerializeToString()
        group_info_buf = self.__client.GetGroupInfo(
            self.uuid,
            jidbuf,
            len(jidbuf),
        )
        model = GetGroupInfoReturnFunction.FromString(group_info_buf.get_bytes())
        if model.Error:
            raise GetGroupInfoError(model.Error)
        return model.GroupInfo

    def get_group_info_from_link(self, code: str) -> GroupInfo:
        model = GetGroupInfoReturnFunction.FromString(
            self.__client.GetGroupInfoFromLink(self.uuid, code.encode()).get_bytes()
        )
        if model.Error:
            raise GetGroupInfoError(model.Error)
        return model.GroupInfo

    def get_group_info_from_invite(
        self, jid: JID, inviter: JID, code: str, expiration: int
    ) -> GroupInfo:
        jidbyte = jid.SerializeToString()
        inviterbyte = inviter.SerializeToString()
        model = GetGroupInfoReturnFunction.FromString(
            self.__client.GetGroupInfoFromInvite(
                self.uuid,
                jidbyte,
                len(jidbyte),
                inviterbyte,
                len(inviterbyte),
                code.encode(),
                expiration,
            ).get_bytes()
        )
        if model.Error:
            raise GetGroupInfoError(model.Error)
        return model.GroupInfo

    def set_group_name(self, jid: JID, name: str) -> str:
        jidbuf = jid.SerializeToString()
        return self.__client.SetGroupName(
            self.uuid, jidbuf, len(jidbuf), ctypes.create_string_buffer(name.encode())
        ).decode()

    def set_group_photo(self, jid: JID, file_or_bytes: typing.Union[str, bytes]) -> str:
        data = get_bytes_from_name_or_url(file_or_bytes)
        jid_buf = jid.SerializeToString()
        response = self.__client.SetGroupPhoto(
            self.uuid, jid_buf, len(jid_buf), data, len(data)
        )
        model = SetGroupPhotoReturnFunction.FromString(response.get_bytes())
        if model.Error:
            raise SetGroupPhotoError(model.Error)
        return model.PictureID

    def leave_group(self, jid: JID) -> str:
        jid_buf = jid.SerializeToString()
        return self.__client.LeaveGroup(self.uuid, jid_buf, len(jid_buf)).decode()

    def get_group_invite_link(self, jid: JID, revoke: bool = False) -> str:
        jid_buf = jid.SerializeToString()
        response = self.__client.GetGroupInviteLink(
            self.uuid, jid_buf, len(jid_buf), revoke
        ).get_bytes()
        model = GetGroupInviteLinkReturnFunction.FromString(response)
        if model.Error:
            raise GetGroupInviteLinkError(model.Error)
        return model.InviteLink

    def join_group_with_link(self, code: str) -> JID:
        resp = self.__client.JoinGroupWithLink(self.uuid, code.encode()).get_bytes()
        model = JoinGroupWithLinkReturnFunction.FromString(resp)
        if model.Error:
            raise InviteLinkError(model.Error)
        return model.Jid

    def join_group_with_invite(
        self, jid: JID, inviter: JID, code: str, expiration: int
    ):
        jidbytes = jid.SerializeToString()
        inviterbytes = inviter.SerializeToString()
        err = self.__client.JoinGroupWithInvite(
            self.uuid,
            jidbytes,
            len(jidbytes),
            inviterbytes,
            len(inviterbytes),
            code.encode(),
            expiration,
        ).decode()
        if err:
            raise JoinGroupWithInviteError(err)

    def link_group(self, parent: JID, child: JID):
        parent_bytes = parent.SerializeToString()
        child_bytes = child.SerializeToString()
        err = self.__client.LinkGroup(
            self.uuid, parent_bytes, len(parent_bytes), child_bytes, len(child_bytes)
        ).decode()
        if err:
            raise LinkGroupError(err)

    def logout(self):
        err = self.__client.Logout(self.uuid).decode()
        if err:
            raise LogoutError(err)

    def mark_read(
        self,
        *message_ids: str,
        chat: JID,
        sender: JID,
        receipt: ReceiptType,
        timestamp: Optional[int] = None,
    ):
        chat_proto = chat.SerializeToString()
        sender_proto = sender.SerializeToString()
        timestamp_args = int(time.time()) if timestamp is None else timestamp
        err = self.__client.MarkRead(
            self.uuid,
            " ".join(message_ids).encode(),
            timestamp_args,
            chat_proto,
            len(chat_proto),
            sender_proto,
            len(sender_proto),
            receipt.value,
        )
        if err:
            raise MarkReadError(err.decode())

    def newsletter_mark_viewed(
        self, jid: JID, message_server_ids: List[MessageServerID]
    ):
        servers = struct.pack(f"{len(message_server_ids)}b", *message_server_ids)
        jid_proto = jid.SerializeToString()
        err = self.__client.NewsletterMarkViewed(
            self.uuid, jid_proto, len(jid_proto), servers, len(servers)
        )
        if err:
            raise NewsletterMarkViewedError(err)

    def newsletter_send_reaction(
        self,
        jid: JID,
        message_server_id: MessageServerID,
        reaction: str,
        message_id: str,
    ):
        jid_proto = jid.SerializeToString()
        err = self.__client.NewsletterSendReaction(
            self.uuid,
            jid_proto,
            len(jid_proto),
            message_server_id,
            reaction.encode(),
            message_id.encode(),
        )
        if err:
            raise NewsletterSendReactionError(err)
        return

    def newsletter_subscribe_live_updates(self, jid: JID) -> int:
        jid_proto = jid.SerializeToString()
        model = snakechat_proto.NewsletterSubscribeLiveUpdatesReturnFunction.FromString(
            self.__client.NewsletterSubscribeLiveUpdates(
                self.uuid, jid_proto, len(jid_proto)
            ).get_bytes()
        )
        if model.Error:
            raise NewsletterSubscribeLiveUpdatesError(model.Error)
        return model.Duration

    def newsletter_toggle_mute(self, jid: JID, mute: bool):
        jid_proto = jid.SerializeToString()
        err = self.__client.NewsletterToggleMute(
            self.uuid, jid_proto, len(jid_proto), mute
        ).decode()
        if err:
            raise NewsletterToggleMuteError(err)

    def resolve_business_message_link(
        self, code: str
    ) -> snakechat_proto.BusinessMessageLinkTarget:
        model = snakechat_proto.ResolveBusinessMessageLinkReturnFunction.FromString(
            self.__client.ResolveBusinessMessageLink(
                self.uuid, code.encode()
            ).get_bytes()
        )
        if model.Error:
            raise ResolveContactQRLinkError(model.Error)
        return model.MessageLinkTarget

    def resolve_contact_qr_link(self, code: str) -> snakechat_proto.ContactQRLinkTarget:
        model = snakechat_proto.ResolveContactQRLinkReturnFunction.FromString(
            self.__client.ResolveContactQRLink(self.uuid, code.encode()).get_bytes()
        )
        if model.Error:
            raise ResolveContactQRLinkError(model.Error)
        return model.ContactQrLink

    def send_app_state(self, patch_info: snakechat_proto.PatchInfo):
        patch = patch_info.SerializeToString()
        err = self.__client.SendAppState(self.uuid, patch, len(patch)).decode()
        if err:
            raise SendAppStateError(err)

    def set_default_disappearing_timer(self, timer: typing.Union[timedelta, int]):
        timestamp = 0
        if isinstance(timer, timedelta):
            timestamp = int(timer.total_seconds() * 1000**3)
        else:
            timestamp = timer
        err = self.__client.SetDefaultDisappearingTimer(self.uuid, timestamp).decode()
        if err:
            raise SetDefaultDisappearingTimerError(err)

    def set_disappearing_timer(self, jid: JID, timer: typing.Union[timedelta, int]):
        timestamp = 0
        jid_proto = jid.SerializeToString()
        if isinstance(timer, timedelta):
            timestamp = int(timer.total_seconds() * 1000**3)
        else:
            timestamp = timer
        err = self.__client.SetDisappearingTimer(
            self.uuid, jid_proto, len(jid_proto), timestamp
        ).decode()
        if err:
            raise SetDisappearingTimerError(err)

    def set_force_activate_delivery_receipts(self, active: bool):
        self.__client.SetForceActiveDeliveryReceipts(self.uuid, active)

    def set_group_announce(self, jid: JID, announce: bool):
        jid_proto = jid.SerializeToString()
        err = self.__client.SetGroupAnnounce(
            self.uuid, jid_proto, len(jid_proto), announce
        ).decode()
        if err:
            raise SetGroupAnnounceError(err)

    def set_group_locked(self, jid: JID, locked: bool):
        jid_proto = jid.SerializeToString()
        err = self.__client.SetGroupLocked(
            self.uuid, jid_proto, len(jid_proto), locked
        ).decode()
        if err:
            raise SetGroupLockedError(err)

    def set_group_topic(self, jid: JID, previous_id: str, new_id: str, topic: str):
        jid_proto = jid.SerializeToString()
        err = self.__client.SetGroupTopic(
            self.uuid,
            jid_proto,
            len(jid_proto),
            previous_id.encode(),
            new_id.encode(),
            topic.encode(),
        ).decode()
        if err:
            raise SetGroupTopicError(err)

    def set_privacy_setting(self, name: PrivacySettingType, value: PrivacySetting):
        err = self.__client.SetPrivacySetting(
            self.uuid, name.value.encode(), value.value.encode()
        ).decode()
        if err:
            raise SetPrivacySettingError(err)

    def set_passive(self, passive: bool):
        err = self.__client.SetPassive(self.uuid, passive)
        if err:
            raise SetPassiveError(err)

    def set_status_message(self, msg: str):
        err = self.__client.SetStatusMessage(self.uuid, msg.encode()).decode()
        if err:
            raise SetStatusMessageError(err)

    def subscribe_presence(self, jid: JID):
        jid_proto = jid.SerializeToString()
        err = self.__client.SubscribePresence(
            self.uuid, jid_proto, len(jid_proto)
        ).decode()
        if err:
            raise SubscribePresenceError(err)

    def unfollow_newsletter(self, jid: JID):
        jid_proto = jid.SerializeToString()
        err = self.__client.UnfollowNewsletter(
            self.uuid, jid_proto, len(jid_proto)
        ).decode()
        if err:
            raise UnfollowNewsletterError(err)

    def unlink_group(self, parent: JID, child: JID):
        parent_proto = parent.SerializeToString()
        child_proto = child.SerializeToString()
        err = self.__client.UnlinkGroup(
            self.uuid, parent_proto, len(parent_proto), child_proto, len(child_proto)
        ).decode()
        if err:
            raise UnlinkGroupError(err)

    def update_blocklist(self, jid: JID, action: BlocklistAction) -> Blocklist:
        jid_proto = jid.SerializeToString()
        model = snakechat_proto.GetBlocklistReturnFunction.FromString(
            self.__client.UpdateBlocklist(
                self.uuid, jid_proto, len(jid_proto), action.value.encode()
            ).get_bytes()
        )
        if model.Error:
            raise UpdateBlocklistError(model.Error)
        return model.Blocklist

    def update_group_participants(
        self, jid: JID, participants_changes: List[JID], action: ParticipantChange
    ) -> RepeatedCompositeFieldContainer[GroupParticipant]:
        jid_proto = jid.SerializeToString()
        jids_proto = snakechat_proto.JIDArray(
            JIDS=participants_changes
        ).SerializeToString()
        model = snakechat_proto.UpdateGroupParticipantsReturnFunction.FromString(
            self.__client.UpdateGroupParticipants(
                self.uuid,
                jid_proto,
                len(jid_proto),
                jids_proto,
                len(jids_proto),
                action.value.encode(),
            ).get_bytes()
        )
        if model.Error:
            raise UpdateGroupParticipantsError(model.Error)
        return model.participants

    def upload_newsletter(self, data: bytes, media_type: MediaType) -> UploadResponse:
        model = UploadReturnFunction.FromString(
            self.__client.UploadNewsletter(
                self.uuid, data, len(data), media_type.value
            ).get_bytes()
        )
        if model.Error:
            raise UploadError(model.Error)
        return model.UploadResponse

    def create_group(
        self,
        name: str,
        participants: List[JID] = [],
        linked_parent: Optional[GroupLinkedParent] = None,
        group_parent: Optional[GroupParent] = None,
    ) -> GroupInfo:
        group_info = ReqCreateGroup(
            name=name, Participants=participants, CreateKey=self.generate_message_id()
        )
        if linked_parent:
            group_info.GroupLinkedParent.MergeFrom(linked_parent)
        if group_parent:
            group_info.GroupParent.MergeFrom(group_parent)
        group_info_buf = group_info.SerializeToString()
        resp = self.__client.CreateGroup(self.uuid, group_info_buf, len(group_info_buf))
        model = GetGroupInfoReturnFunction.FromString(resp.get_bytes())
        if model.Error:
            raise CreateGroupError(model.Error)
        return model.GroupInfo

    def get_group_request_participants(
        self, jid: JID
    ) -> RepeatedCompositeFieldContainer[JID]:
        jidbyte = jid.SerializeToString()
        model = snakechat_proto.GetGroupRequestParticipantsReturnFunction.FromString(
            self.__client.GetGroupRequestParticipants(
                self.uuid, jidbyte, len(jidbyte)
            ).get_bytes()
        )
        if model.Error:
            raise GetGroupRequestParticipantsError(model.Error)
        return model.Participants

    def get_joined_groups(self) -> RepeatedCompositeFieldContainer[GroupInfo]:
        model = snakechat_proto.GetJoinedGroupsReturnFunction.FromString(
            self.__client.GetJoinedGroups(self.uuid).get_bytes()
        )
        if model.Error:
            raise GetJoinedGroupsError(model.Error)
        return model.Group

    def create_newsletter(
        self, name: str, description: str, picture: typing.Union[str, bytes]
    ) -> NewsletterMetadata:
        protobuf = snakechat_proto.CreateNewsletterParams(
            Name=name,
            Description=description,
            Picture=get_bytes_from_name_or_url(picture),
        ).SerializeToString()
        model = snakechat_proto.CreateNewsLetterReturnFunction.FromString(
            self.__client.CreateNewsletter(
                self.uuid, protobuf, len(protobuf)
            ).get_bytes()
        )
        if model.Error:
            raise CreateNewsletterError(model.Error)
        return model.NewsletterMetadata

    def follow_newsletter(self, jid: JID):


        jidbyte = jid.SerializeToString()
        err = self.__client.FollowNewsletter(self.uuid, jidbyte, len(jidbyte)).decode()
        if err:
            raise FollowNewsletterError(err)

    def get_newsletter_info_with_invite(self, key: str) -> NewsletterMetadata:
        model = snakechat_proto.CreateNewsLetterReturnFunction.FromString(
            self.__client.GetNewsletterInfoWithInvite(
                self.uuid, key.encode()
            ).get_bytes()
        )
        if model.Error:
            raise GetNewsletterInfoWithInviteError(model.Error)
        return model.NewsletterMetadata

    def get_newsletter_message_update(
        self, jid: JID, count: int, since: int, after: int
    ) -> RepeatedCompositeFieldContainer[NewsletterMessage]:
        jidbyte = jid.SerializeToString()
        model = snakechat_proto.GetNewsletterMessageUpdateReturnFunction.FromString(
            self.__client.GetNewsletterMessageUpdate(
                self.uuid, jidbyte, len(jidbyte), count, since, after
            ).get_bytes()
        )
        if model.Error:
            raise GetNewsletterMessageUpdateError(model.Error)
        return model.NewsletterMessage

    def get_newsletter_messages(
        self, jid: JID, count: int, before: MessageServerID
    ) -> RepeatedCompositeFieldContainer[NewsletterMessage]:
        jidbyte = jid.SerializeToString()
        model = snakechat_proto.GetNewsletterMessageUpdateReturnFunction.FromString(
            self.__client.GetNewsletterMessages(
                self.uuid, jidbyte, len(jidbyte), count, before
            ).get_bytes()
        )
        if model.Error:
            raise GetNewsletterMessagesError(model.Error)
        return model.NewsletterMessage

    def get_privacy_settings(self) -> PrivacySettings:
        return snakechat_proto.PrivacySettings.FromString(
            self.__client.GetPrivacySettings(self.uuid).get_bytes()
        )

    def get_profile_picture(
        self,
        jid: JID,
        extra: snakechat_proto.GetProfilePictureParams = snakechat_proto.GetProfilePictureParams(),
    ) -> ProfilePictureInfo:
        jid_bytes = jid.SerializeToString()
        extra_bytes = extra.SerializeToString()
        model = snakechat_proto.GetProfilePictureReturnFunction.FromString(
            self.__client.GetProfilePicture(
                self.uuid,
                jid_bytes,
                len(jid_bytes),
                extra_bytes,
                len(extra_bytes),
            ).get_bytes()
        )
        if model.Error:
            raise GetProfilePictureError(model)
        return model.Picture

    def get_status_privacy(
        self,
    ) -> RepeatedCompositeFieldContainer[StatusPrivacy]:
        model = snakechat_proto.GetStatusPrivacyReturnFunction.FromString(
            self.__client.GetStatusPrivacy(self.uuid).get_bytes()
        )
        if model.Error:
            raise GetStatusPrivacyError(model.Error)
        return model.StatusPrivacy

    def get_sub_groups(
        self, community: JID
    ) -> RepeatedCompositeFieldContainer[GroupLinkTarget]:
        jid = community.SerializeToString()
        model = snakechat_proto.GetSubGroupsReturnFunction.FromString(
            self.__client.GetSubGroups(self.uuid, jid, len(jid)).get_bytes()
        )
        if model.Error:
            raise GetSubGroupsError(model.Error)
        return model.GroupLinkTarget

    def get_subscribed_newletters(
        self,
    ) -> RepeatedCompositeFieldContainer[NewsletterMetadata]:
        model = snakechat_proto.GetSubscribedNewslettersReturnFunction.FromString(
            self.__client.GetSubscribedNewsletters(self.uuid).get_bytes()
        )
        if model.Error:
            raise GetSubscribedNewslettersError(model.Error)
        return model.Newsletter

    def get_user_devices(self, *jids: JID) -> RepeatedCompositeFieldContainer[JID]:
        jids_ = snakechat_proto.JIDArray(JIDS=jids).SerializeToString()
        model = snakechat_proto.GetUserDevicesreturnFunction.FromString(
            self.__client.GetUserDevices(self.uuid, jids_, len(jids_)).get_bytes()
        )
        if model.Error:
            raise GetUserDevicesError(model.Error)
        return model.JID

    def get_blocklist(self) -> Blocklist:
        model = snakechat_proto.GetBlocklistReturnFunction.FromString(
            self.__client.GetBlocklist(self.uuid).get_bytes()
        )
        if model.Error:
            raise GetBlocklistError(model.Error)
        return model.Blocklist

    def get_me(self) -> Device:
        return Device.FromString(self.__client.GetMe(self.uuid).get_bytes())

    def get_contact_qr_link(self, revoke: bool = False) -> str:
        model = snakechat_proto.GetContactQRLinkReturnFunction.FromString(
            self.__client.GetContactQRLink(self.uuid, revoke).get_bytes()
        )
        if model.Error:
            raise GetContactQrLinkError(model.Error)
        return model.Link

    def get_linked_group_participants(
        self, community: JID
    ) -> RepeatedCompositeFieldContainer[JID]:
        jidbyte = community.SerializeToString()
        model = snakechat_proto.GetGroupRequestParticipantsReturnFunction.FromString(
            self.__client.GetLinkedGroupsParticipants(
                self.uuid, jidbyte, len(jidbyte)
            ).get_bytes()
        )
        if model.Error:
            raise GetLinkedGroupParticipantsError(model.Error)
        return model.Participants

    def get_newsletter_info(self, jid: JID) -> snakechat_proto.NewsletterMetadata:
        jidbyte = jid.SerializeToString()
        model = snakechat_proto.CreateNewsLetterReturnFunction.FromString(
            self.__client.GetNewsletterInfo(
                self.uuid, jidbyte, len(jidbyte)
            ).get_bytes()
        )
        if model.Error:
            raise GetNewsletterInfoError(model.Error)
        return model.NewsletterMetadata

    def PairPhone(
        self,
        phone: str,
        show_push_notification: bool,
        client_name: ClientName = ClientName.LINUX,
        client_type: Optional[ClientType] = None,
    ):

        if client_type is None:
            if self.device_props is None:
                client_type = ClientType.FIREFOX
            else:
                try:
                    client_type = ClientType(self.device_props.platformType)
                except ValueError:
                    client_type = ClientType.FIREFOX

        pl = snakechat_proto.PairPhoneParams(
            phone=phone,
            clientDisplayName="%s (%s)" % (client_type.name, client_name.name),
            clientType=client_type.value,
            showPushNotification=show_push_notification,
        )
        payload = pl.SerializeToString()
        d = bytearray(list(self.event.list_func))

        log.debug("trying connect to whatsapp servers")

        deviceprops = (
            DeviceProps(os="snakechat", platformType=DeviceProps.SAFARI)
            if self.device_props is None
            else self.device_props
        ).SerializeToString()

        jidbuf_size = 0
        jidbuf = b""
        if self.jid:
            jidbuf = self.jid.SerializeToString()
            jidbuf_size = len(jidbuf)

        self.__client.snakechat(
            self.name.encode(),
            self.uuid,
            jidbuf,
            jidbuf_size,
            LogLevel.from_logging(log.level).level,
            func_string(self.__onQr),
            func_string(self.__onLoginStatus),
            func_callback_bytes(self.event.execute),
            (ctypes.c_char * self.event.list_func.__len__()).from_buffer(d),
            len(d),
            func(self.event.blocking_func),
            deviceprops,
            len(deviceprops),
            payload,
            len(payload),
        )

    def get_message_for_retry(
        self, requester: JID, to: JID, message_id: str
    ) -> typing.Union[None, Message]:
        requester_buf = requester.SerializeToString()
        to_buf = to.SerializeToString()
        model = snakechat_proto.GetMessageForRetryReturnFunction.FromString(
            self.__client.GetMessageForRetry(
                self.uuid,
                requester_buf,
                len(requester_buf),
                to_buf,
                len(to_buf),
                message_id.encode(),
            ).get_bytes()
        )
        if not model.isEmpty:
            return model.Message

    def connect(self):
        # Convert the list of functions to a bytearray
        d = bytearray(list(self.event.list_func))
        log.debug("Intentando conectarse a WhatsApp.")
        # Set device properties
        deviceprops = (
            DeviceProps(os="snakechat", platformType=DeviceProps.SAFARI)
            if self.device_props is None
            else self.device_props
        ).SerializeToString()

        jidbuf_size = 0
        jidbuf = b""
        if self.jid:
            jidbuf = self.jid.SerializeToString()
            jidbuf_size = len(jidbuf)

        # Initiate connection to the server
        self.__client.snakechat(
            self.name.encode(),
            self.uuid,
            jidbuf,
            jidbuf_size,
            LogLevel.from_logging(log.level).level,
            func_string(self.__onQr),
            func_string(self.__onLoginStatus),
            func_callback_bytes(self.event.execute),
            (ctypes.c_char * len(self.event.list_func)).from_buffer(d),
            len(d),
            func(self.event.blocking_func),
            deviceprops,
            len(deviceprops),
            b"",
            0,
        )

    def disconnect(self) -> None:
        self.__client.Disconnect(self.uuid)



class ClientFactory:
    def __init__(self, database_name: str = 'snakechat.db') -> None:
        self.database_name = database_name
        self.clients: list[NewClient] = []
        self.event = EventsManager(self)

    @staticmethod
    def get_all_devices_from_db(db: str) -> List["Device"]:
        c_string = gocode.GetAllDevices(db.encode()).decode()
        if not c_string:
            return []
        
        class Device:
            def __init__(self, JID: JID, PushName: str, BussinessName: str = None, Initialized: bool = None):
                self.JID = JID
                self.PushName = PushName
                self.BusinessName = BussinessName
                self.Initialized = Initialized

        devices: list[Device] = []

        for device_str in c_string.split('|\u0001|'):
            id, push_name, bussniess_name, initialized = device_str.split(',')
            id, server = id.split('@')
            jid = build_jid(id, server)

            device = Device(jid, push_name, bussniess_name, initialized == 'true')
            devices.append(device)
        
        return devices

    def get_all_devices(self) -> List["Device"]:
        return self.get_all_devices_from_db(self.database_name)

    def new_client(self, jid: JID = None, uuid: str = None, props: Optional[DeviceProps] = None) -> NewClient:

        if not jid and not uuid:
            # you must at least provide a uuid to make sure the client is unique
            raise Exception("JID and UUID cannot be none")

        client = NewClient(self.database_name, jid, props, uuid)
        self.clients.append(client)    
        return client

    def run(self):
        for client in self.clients:
            Thread(
                target=client.connect,
                daemon=True,
                name=client.uuid,
            ).start()

        Event.default_blocking(None)
