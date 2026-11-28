# Vinculación QR (pair-device / pair-success) y persistencia de credenciales
import base64
import hashlib
import hmac
import json
import os
import random
import struct
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519

from protobuf import (
    HandshakeMessage, ClientPayload, DeviceProps,
    ADVSignedDeviceIdentityHMAC, ADVSignedDeviceIdentity, ADVDeviceIdentity, HOSTED,
)
from crypto.keys import generate_x25519_keypair, xeddsa_sign
from binary import BinaryNode

try:
    import qrcode
except ImportError:
    qrcode = None

CREDS_PATH = Path(__file__).resolve().parent / "creds.json"

def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))

class PairingState:

    def __init__(self, wa_version: tuple[int, int, int], creds_path: Path = CREDS_PATH):
        self.wa_version = wa_version
        self.creds_path = creds_path

        self.jid: str | None = None
        self.lid: str | None = None
        self.account_bytes: bytes | None = None
        self.key_index: int | None = None

        if self.creds_path.exists():
            self._load_creds()
        else:
            self._init_fresh_keys()

    @property
    def is_registered(self) -> bool:
        return bool(self.jid)

    def _init_fresh_keys(self):
        self.static_priv, self.static_priv_bytes, self.static_pub = generate_x25519_keypair()
        _, self.ident_priv_bytes, self.ident_pub_bytes = generate_x25519_keypair()
        _, self.skey_priv_bytes, self.skey_pub_bytes = generate_x25519_keypair()
        self.adv_secret_key = os.urandom(32)
        self.reg_id = random.randint(1, 16380)

    def _load_creds(self):
        data = json.loads(self.creds_path.read_text(encoding="utf-8"))
        self.static_priv_bytes = _b64d(data["static_priv"])
        self.static_priv = x25519.X25519PrivateKey.from_private_bytes(self.static_priv_bytes)
        self.static_pub = _b64d(data["static_pub"])
        self.ident_priv_bytes = _b64d(data["ident_priv"])
        self.ident_pub_bytes = _b64d(data["ident_pub"])
        self.skey_priv_bytes = _b64d(data["skey_priv"])
        self.skey_pub_bytes = _b64d(data["skey_pub"])
        self.adv_secret_key = _b64d(data["adv_secret_key"])
        self.reg_id = int(data["reg_id"])
        self.jid = data.get("jid")
        self.lid = data.get("lid")
        self.key_index = data.get("key_index")
        if data.get("account"):
            self.account_bytes = _b64d(data["account"])
        print(f"[+] Sesión cargada desde {self.creds_path} (JID: {self.jid})")

    def save_creds(self):
        self.creds_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "static_priv": _b64e(self.static_priv_bytes),
            "static_pub": _b64e(self.static_pub),
            "ident_priv": _b64e(self.ident_priv_bytes),
            "ident_pub": _b64e(self.ident_pub_bytes),
            "skey_priv": _b64e(self.skey_priv_bytes),
            "skey_pub": _b64e(self.skey_pub_bytes),
            "adv_secret_key": _b64e(self.adv_secret_key),
            "reg_id": self.reg_id,
            "jid": self.jid,
            "lid": self.lid,
            "key_index": self.key_index,
            "account": _b64e(self.account_bytes) if self.account_bytes else None,
        }
        self.creds_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[+] Credenciales guardadas en {self.creds_path}")

    def _fill_base_client_payload(self, cp: ClientPayload):
        cp.connect_type = ClientPayload.WIFI_UNKNOWN
        cp.connect_reason = ClientPayload.USER_ACTIVATED

        cp.user_agent.platform = ClientPayload.UserAgent.WEB
        cp.user_agent.app_version.primary = self.wa_version[0]
        cp.user_agent.app_version.secondary = self.wa_version[1]
        cp.user_agent.app_version.tertiary = self.wa_version[2]
        cp.user_agent.mcc = "000"
        cp.user_agent.mnc = "000"
        cp.user_agent.os_version = "0.1"
        cp.user_agent.device = "Desktop"
        cp.user_agent.os_build_number = "0.1"
        cp.user_agent.release_channel = ClientPayload.UserAgent.RELEASE
        cp.user_agent.locale_language_iso6391 = "en"
        cp.user_agent.locale_country_iso31661_alpha2 = "US"

        cp.web_info.web_sub_platform = ClientPayload.WebInfo.WEB_BROWSER

    def build_client_payload(self) -> bytes:
        cp = ClientPayload()
        self._fill_base_client_payload(cp)

        if self.is_registered and self.jid:
            user_part = self.jid.split("@")[0]
            if ":" in user_part:
                phone, dev_id = user_part.split(":", 1)
                cp.username = int(phone)
                cp.device = int(dev_id)
            else:
                cp.username = int(user_part)
            cp.passive = False
            cp.pull = True
            return cp.SerializeToString()

        dev_props = DeviceProps()
        dev_props.os = "Windows"
        dev_props.version.primary = 10
        dev_props.version.secondary = 0
        dev_props.version.tertiary = 0
        dev_props.platform_type = DeviceProps.CHROME
        dev_props.require_full_sync = False
        dev_props_bytes = dev_props.SerializeToString()

        skey_sig = xeddsa_sign(self.ident_priv_bytes, b"\x05" + self.skey_pub_bytes)
        build_hash = hashlib.md5(
            f"{self.wa_version[0]}.{self.wa_version[1]}.{self.wa_version[2]}".encode()
        ).digest()

        cp.passive = False
        cp.device_pairing_data.e_regid = struct.pack(">I", self.reg_id)
        cp.device_pairing_data.e_keytype = b"\x05"
        cp.device_pairing_data.e_ident = self.ident_pub_bytes
        cp.device_pairing_data.e_skey_id = struct.pack(">I", 1)[1:]
        cp.device_pairing_data.e_skey_val = self.skey_pub_bytes
        cp.device_pairing_data.e_skey_sig = skey_sig
        cp.device_pairing_data.build_hash = build_hash
        cp.device_pairing_data.device_props = dev_props_bytes

        return cp.SerializeToString()

    def build_qr_string(self, ref_str: str) -> str:
        return ",".join([
            ref_str,
            _b64e(self.static_pub),
            _b64e(self.ident_pub_bytes),
            _b64e(self.adv_secret_key),
        ])

    @staticmethod
    def print_qr_code(qr_data: str):
        print("\n" + "=" * 60)
        print("ESCANEA ESTE CÓDIGO QR EN WHATSAPP -> DISPOSITIVOS VINCULADOS")
        print("=" * 60)
        if qrcode:
            qr = qrcode.QRCode(border=1)
            qr.add_data(qr_data)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        else:
            print("[!] Instala 'qrcode' para ver el QR dibujado: py -m pip install qrcode")
        print(f"\n[QR RAW]: {qr_data}\n")

    def _process_pair_success(self, msg_id: str, pair_success: BinaryNode) -> BinaryNode:
        device_node = pair_success.get_child("device")
        identity_node = pair_success.get_child("device-identity")

        if not device_node or not identity_node or not isinstance(identity_node.content, bytes):
            raise ValueError("Nodo pair-success incompleto")

        self.jid = device_node.attrs.get("jid")
        self.lid = device_node.attrs.get("lid")

        hmac_msg = ADVSignedDeviceIdentityHMAC()
        hmac_msg.ParseFromString(identity_node.content)

        is_hosted = hmac_msg.account_type == HOSTED
        hmac_prefix = b"\x06\x05" if is_hosted else b""
        expected_hmac = hmac.new(
            self.adv_secret_key, hmac_prefix + hmac_msg.details, hashlib.sha256
        ).digest()

        if not hmac.compare_digest(expected_hmac, hmac_msg.hmac):
            raise ValueError("HMAC de device-identity inválido")

        account = ADVSignedDeviceIdentity()
        account.ParseFromString(hmac_msg.details)

        device_prefix = b"\x06\x06" if is_hosted else b"\x06\x01"
        device_msg = (
            device_prefix
            + account.details
            + self.ident_pub_bytes
            + account.account_signature_key
        )
        account.device_signature = xeddsa_sign(self.ident_priv_bytes, device_msg)

        dev_identity = ADVDeviceIdentity()
        dev_identity.ParseFromString(account.details)
        self.key_index = dev_identity.key_index

        self.account_bytes = account.SerializeToString()
        self.save_creds()

        reply_account = ADVSignedDeviceIdentity()
        reply_account.details = account.details
        reply_account.account_signature = account.account_signature
        reply_account.device_signature = account.device_signature
        if is_hosted:
            reply_account.account_signature_key = account.account_signature_key

        print(f"[+] Dispositivo firmado y vinculado: {self.jid} (key-index={self.key_index})")

        return BinaryNode(
            tag="iq",
            attrs={
                "to": "s.whatsapp.net",
                "type": "result",
                "id": msg_id,
            },
            content=[
                BinaryNode(
                    tag="pair-device-sign",
                    content=[
                        BinaryNode(
                            tag="device-identity",
                            attrs={"key-index": str(self.key_index)},
                            content=reply_account.SerializeToString(),
                        )
                    ],
                )
            ],
        )

    def handle_node(self, node: BinaryNode) -> BinaryNode | None:
        if node.tag != "iq" or node.attrs.get("type") != "set":
            return None

        msg_id = node.attrs.get("id", "")

        pair_device = node.get_child("pair-device")
        if pair_device:
            ack = BinaryNode(
                tag="iq",
                attrs={
                    "to": "s.whatsapp.net",
                    "type": "result",
                    "id": msg_id,
                },
            )
            refs = pair_device.get_children("ref")
            if refs:
                ref_raw = refs[0].content
                ref_str = (
                    ref_raw.decode("utf-8")
                    if isinstance(ref_raw, bytes)
                    else str(ref_raw)
                )
                self.print_qr_code(self.build_qr_string(ref_str))
            return ack

        pair_success = node.get_child("pair-success")
        if pair_success:
            print("\n[!!!] ¡PAIR-SUCCESS RECIBIDO! Firmando identidad del dispositivo...")
            return self._process_pair_success(msg_id, pair_success)

        return None
