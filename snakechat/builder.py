from .proto import snakechat_pb2 as snakechat
from .proto.waE2E.WAWebProtobufsE2E_pb2 import (
    Message,
    FutureProofMessage,
    ProtocolMessage,
    PeerDataOperationRequestMessage,
    PeerDataOperationRequestType,
)
from .proto.waCommon.WACommon_pb2 import MessageKey
from .const import DEFAULT_USER_SERVER
from .utils.jid import Jid2String, JIDToNonAD
import time


def build_edit(chat: snakechat.JID, message_id: str, new_message: Message) -> Message:
    return Message(
        editedMessage=FutureProofMessage(
            message=Message(
                protocolMessage=ProtocolMessage(
                    key=MessageKey(
                        fromMe=True,
                        ID=message_id,
                        remoteJID=Jid2String(chat),
                    ),
                    type=ProtocolMessage.MESSAGE_EDIT,
                    editedMessage=new_message,
                    timestampMS=int(time.time() * 1000),
                )
            )
        )
    )


def build_revoke(
    chat: snakechat.JID, sender: snakechat.JID, id: str, myJID: snakechat.JID
) -> Message:
    msgKey = MessageKey(
        fromMe=myJID.User == sender.User,
        ID=id,
        remoteJID=Jid2String(chat),
    )
    if not sender.IsEmpty and not msgKey.fromMe and chat.Server != DEFAULT_USER_SERVER:
        msgKey.participant = Jid2String(JIDToNonAD(sender))
    return Message(
        protocolMessage=ProtocolMessage(type=ProtocolMessage.REVOKE, key=msgKey)
    )


def build_history_sync_request(
    message_info: snakechat.MessageInfo, count: int
) -> Message:
    return Message(
        protocolMessage=ProtocolMessage(
            type=ProtocolMessage.PEER_DATA_OPERATION_REQUEST_MESSAGE,
            peerDataOperationRequestMessage=PeerDataOperationRequestMessage(
                peerDataOperationRequestType=PeerDataOperationRequestType.HISTORY_SYNC_ON_DEMAND,
                historySyncOnDemandRequest=PeerDataOperationRequestMessage.HistorySyncOnDemandRequest(
                    chatJID=Jid2String(message_info.MessageSource.Chat),
                    oldestMsgID=message_info.ID,
                    oldestMsgFromMe=message_info.MessageSource.IsFromMe,
                    onDemandMsgCount=count,
                    oldestMsgTimestampMS=message_info.Timestamp,
                ),
            ),
        )
    )
