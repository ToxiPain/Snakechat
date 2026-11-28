# Motor Signal v3: X3DH + Double Ratchet + Sender Key para cifrar/descifrar mensajes
import base64
import hashlib
import hmac
import json
import os
import random
from pathlib import Path

from cryptography.hazmat.primitives import hashes, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from protobuf import (
    WAMessage,
    SignalMessage,
    PreKeySignalMessage,
    SenderKeyMessage,
    SenderKeyDistributionMessage,
)
from crypto.keys import generate_x25519_keypair, xeddsa_sign

SESSIONS_PATH = Path(__file__).resolve().parent.parent / "state" / "sessions.json"
SENDER_KEYS_PATH = Path(__file__).resolve().parent.parent / "state" / "sender_keys.json"


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _strip_key_prefix(key_bytes: bytes) -> bytes:
    return key_bytes[1:] if len(key_bytes) == 33 and key_bytes[0] == 0x05 else key_bytes


def _add_key_prefix(key_bytes: bytes) -> bytes:
    return key_bytes if len(key_bytes) == 33 else (b"\x05" + key_bytes)


def _dh(priv_bytes: bytes, pub_bytes: bytes) -> bytes:
    priv = x25519.X25519PrivateKey.from_private_bytes(priv_bytes)
    pub = x25519.X25519PublicKey.from_public_bytes(_strip_key_prefix(pub_bytes))
    return priv.exchange(pub)


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    ).derive(ikm)


def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def _aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _unpad_wa_plaintext(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if 0 < pad_len <= len(data):
        return data[:-pad_len]
    return data


def _pad_wa_plaintext(data: bytes) -> bytes:
    pad_len = random.randint(1, 16)
    return data + bytes([pad_len]) * pad_len


# ─── Sender Key Chain helpers (grupos) ──────────────────────────────────────

def _derive_sender_key_step(chain_key: bytes) -> tuple[bytes, bytes]:
    """
    Avanza la cadena de sender key un paso.
    Retorna (message_key_seed, next_chain_key).
    """
    msg_key = _hmac_sha256(chain_key, b"\x01")
    next_chain = _hmac_sha256(chain_key, b"\x02")
    return msg_key, next_chain


def _sender_msg_key_to_cipher_keys(msg_key: bytes) -> tuple[bytes, bytes]:
    """
    Expande el message_key_seed de grupo a (cipher_key 32B, iv 16B).
    En libsignal / Baileys / Whatsmeow (WhisperGroup):
      bytes  0..16 = IV (16 bytes)
      bytes 16..48 = Cipher Key (32 bytes)
    """
    derived = _hkdf_sha256(msg_key, salt=b"\x00" * 32, info=b"WhisperGroup", length=48)
    iv = derived[:16]
    cipher_key = derived[16:48]
    return cipher_key, iv


def _encode_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


class SignalSessionManager:

    def __init__(
        self,
        ident_priv_bytes: bytes,
        ident_pub_bytes: bytes,
        skey_priv_bytes: bytes,
        prekeys,
        sessions_path: Path = SESSIONS_PATH,
        sender_keys_path: Path = SENDER_KEYS_PATH,
    ):
        self.ident_priv_bytes = ident_priv_bytes
        self.ident_pub_bytes = ident_pub_bytes
        self.skey_priv_bytes = skey_priv_bytes
        self.prekeys = prekeys
        self.sessions_path = sessions_path
        self.sender_keys_path = sender_keys_path

        self.sessions: dict[str, dict] = {}
        if self.sessions_path.exists():
            self.sessions = json.loads(self.sessions_path.read_text(encoding="utf-8"))

        # sender_keys[group_jid][sender_jid] = {id, chain_key, iteration, signing_key_pub}
        self.sender_keys: dict[str, dict[str, dict]] = {}
        if self.sender_keys_path.exists():
            self.sender_keys = json.loads(self.sender_keys_path.read_text(encoding="utf-8"))

    def _save_sessions(self):
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_path.write_text(json.dumps(self.sessions, indent=2), encoding="utf-8")

    def _save_sender_keys(self):
        self.sender_keys_path.parent.mkdir(parents=True, exist_ok=True)
        self.sender_keys_path.write_text(json.dumps(self.sender_keys, indent=2), encoding="utf-8")

    # ─── Sender Key Distribution ─────────────────────────────────────────────

    def process_sender_key_distribution(
        self,
        group_jid: str,
        sender_jid: str,
        skdm_bytes: bytes,
    ) -> None:
        """
        Procesa un SenderKeyDistributionMessage y guarda la sender key
        para poder descifrar mensajes de grupo de ese sender al instante.
        """
        try:
            skdm = SenderKeyDistributionMessage()
            skdm.ParseFromString(skdm_bytes)
        except Exception as e:
            print(f"[!] No se pudo parsear SenderKeyDistributionMessage de {sender_jid}: {e}")
            return

        if not skdm.chain_key:
            print(f"[!] SenderKeyDistributionMessage sin chain_key de {sender_jid}")
            return

        group_map = self.sender_keys.setdefault(group_jid, {})
        group_map[sender_jid] = {
            "id": skdm.id,
            "chain_key": _b64e(skdm.chain_key),
            "iteration": skdm.iteration,
            "signing_key_pub": _b64e(skdm.signing_key),
        }
        self._save_sender_keys()
        print(
            f"[*] Sender key de {sender_jid} en grupo {group_jid} registrada "
            f"(id={skdm.id}, iter={skdm.iteration})"
        )

    # ─── Descifrado de Sender Key Message (grupos) ───────────────────────────

    def decrypt_skmsg(self, group_jid: str, sender_jid: str, raw_skmsg: bytes) -> bytes:
        """
        Descifra un SenderKeyMessage (enc type="skmsg") de un grupo.
        """
        base_group = group_jid.split("@")[0].split(":")[0] + "@" + group_jid.split("@")[1]
        base_sender = sender_jid.split("@")[0].split(":")[0] + "@" + (
            sender_jid.split("@")[1] if "@" in sender_jid else "s.whatsapp.net"
        )

        group_map = self.sender_keys.get(group_jid) or self.sender_keys.get(base_group, {})
        sk_data = group_map.get(sender_jid) or group_map.get(base_sender)

        if not sk_data:
            raise ValueError(
                f"No hay sender key guardada para {sender_jid} en {group_jid}. "
                "Esperando SenderKeyDistributionMessage."
            )

        # Formato libsignal: 1 byte versión (0x33) + proto + 64 bytes firma XEdDSA
        if len(raw_skmsg) < 66 or raw_skmsg[0] != 0x33:
            raise ValueError(f"SenderKeyMessage inválido ({len(raw_skmsg)} bytes)")

        skm = SenderKeyMessage()
        try:
            skm.ParseFromString(raw_skmsg[1:-64])
        except Exception as e:
            raise ValueError(f"Error parseando SenderKeyMessage: {e}") from e

        iteration = skm.iteration
        ciphertext = skm.ciphertext

        chain_key = _b64d(sk_data["chain_key"])
        saved_iter = int(sk_data["iteration"])

        if iteration < saved_iter:
            raise ValueError(
                f"Iteración {iteration} ya fue procesada (guardada={saved_iter}) para {sender_jid}"
            )

        for _ in range(iteration - saved_iter):
            _, chain_key = _derive_sender_key_step(chain_key)

        msg_key, next_chain = _derive_sender_key_step(chain_key)
        cipher_key, iv = _sender_msg_key_to_cipher_keys(msg_key)

        plaintext = _aes_cbc_decrypt(cipher_key, iv, ciphertext)
        plaintext = _unpad_wa_plaintext(plaintext)

        sk_data["chain_key"] = _b64e(next_chain)
        sk_data["iteration"] = iteration + 1
        for k in (group_jid, base_group):
            if k in self.sender_keys:
                for s in (sender_jid, base_sender):
                    if s in self.sender_keys[k]:
                        self.sender_keys[k][s] = sk_data
        self._save_sender_keys()

        return plaintext

    # ─── Cifrado de Sender Key Message (grupos) ──────────────────────────────

    def get_or_create_own_sender_key(self, group_jid: str) -> tuple[dict, bytes]:
        """
        Obtiene o crea nuestra propia SenderKey para un grupo y devuelve
        (sk_data, axolotl_skdm_bytes) listos para distribuir a los participantes.
        """
        group_map = self.sender_keys.setdefault(group_jid, {})
        sk = group_map.get("__self__")
        if not sk:
            _, sig_priv, sig_pub = generate_x25519_keypair()
            sk = {
                "id": random.randint(1, 2147483647),
                "iteration": 0,
                "chain_key": _b64e(os.urandom(32)),
                "signing_key_priv": _b64e(sig_priv),
                "signing_key_pub": _b64e(sig_pub),
            }
            group_map["__self__"] = sk
            self._save_sender_keys()

        proto = (
            _encode_varint((1 << 3) | 0) + _encode_varint(sk["id"])
            + _encode_varint((2 << 3) | 0) + _encode_varint(sk["iteration"])
            + _encode_varint((3 << 3) | 2) + _encode_varint(32) + _b64d(sk["chain_key"])
            + _encode_varint((4 << 3) | 2)
            + _encode_varint(33)
            + _add_key_prefix(_b64d(sk["signing_key_pub"]))
        )
        return sk, b"\x33" + proto

    def encrypt_skmsg(self, group_jid: str, plaintext_proto: bytes) -> tuple[bytes, bytes]:
        """
        Cifra un WAMessage para un grupo usando nuestra SenderKey.
        Retorna (skmsg_bytes, axolotl_skdm_bytes).
        """
        sk, skdm_bytes = self.get_or_create_own_sender_key(group_jid)
        chain_key = _b64d(sk["chain_key"])
        iteration = int(sk["iteration"])

        msg_key, next_chain = _derive_sender_key_step(chain_key)
        cipher_key, iv = _sender_msg_key_to_cipher_keys(msg_key)

        padded = _pad_wa_plaintext(plaintext_proto)
        ciphertext = _aes_cbc_encrypt(cipher_key, iv, padded)

        proto = (
            _encode_varint((1 << 3) | 0) + _encode_varint(sk["id"])
            + _encode_varint((2 << 3) | 0) + _encode_varint(iteration)
            + _encode_varint((3 << 3) | 2) + _encode_varint(len(ciphertext)) + ciphertext
        )
        payload = b"\x33" + proto
        sig = xeddsa_sign(_b64d(sk["signing_key_priv"]), payload)

        sk["chain_key"] = _b64e(next_chain)
        sk["iteration"] = iteration + 1
        self.sender_keys[group_jid]["__self__"] = sk
        self._save_sender_keys()

        return payload + sig, skdm_bytes

    # ─── Signal (pkmsg / msg) ────────────────────────────────────────────────

    def _decrypt_signal_message(self, jid: str, raw_msg: bytes, session: dict) -> bytes:
        if len(raw_msg) < 10 or raw_msg[0] != 0x33:
            raise ValueError(f"Versión de SignalMessage inválida: {raw_msg[:1].hex()}")

        body = raw_msg[1:-8]
        sig_msg = SignalMessage()
        sig_msg.ParseFromString(body)

        their_ratchet = _strip_key_prefix(sig_msg.ratchet_key)
        counter = sig_msg.counter

        root_key = _b64d(session["root_key"])
        remote_ratchet = _b64d(session["remote_ratchet"]) if session.get("remote_ratchet") else None
        recv_chain_key = _b64d(session["recv_chain_key"]) if session.get("recv_chain_key") else None
        recv_counter = int(session.get("recv_counter", 0))

        if remote_ratchet != their_ratchet or recv_chain_key is None:
            local_priv = (
                _b64d(session["local_ratchet_priv"])
                if session.get("local_ratchet_priv")
                else self.skey_priv_bytes
            )
            dh_out = _dh(local_priv, their_ratchet)
            derived = _hkdf_sha256(dh_out, salt=root_key, info=b"WhisperRatchet", length=64)
            root_key = derived[:32]
            recv_chain_key = derived[32:64]
            remote_ratchet = their_ratchet
            recv_counter = 0
            session["send_chain_key"] = None
            session["previous_counter"] = int(session.get("send_counter", 0))
            session["send_counter"] = 0

        if counter < recv_counter:
            raise ValueError(f"Contador atrasado ({counter} < {recv_counter}) para {jid}")

        chain_key = recv_chain_key
        for _ in range(counter - recv_counter):
            chain_key = _hmac_sha256(chain_key, b"\x02")

        msg_key_seed = _hmac_sha256(chain_key, b"\x01")
        next_chain_key = _hmac_sha256(chain_key, b"\x02")

        keys = _hkdf_sha256(msg_key_seed, salt=b"\x00" * 32, info=b"WhisperMessageKeys", length=80)
        cipher_key = keys[0:32]
        iv = keys[64:80]

        plaintext_padded = _aes_cbc_decrypt(cipher_key, iv, sig_msg.ciphertext)
        plaintext = _unpad_wa_plaintext(plaintext_padded)

        session["root_key"] = _b64e(root_key)
        session["remote_ratchet"] = _b64e(remote_ratchet)
        session["recv_chain_key"] = _b64e(next_chain_key)
        session["recv_counter"] = counter + 1
        self.sessions[jid] = session
        self._save_sessions()

        return plaintext

    def decrypt_pkmsg(self, jid: str, raw_pkmsg: bytes) -> bytes:
        if len(raw_pkmsg) < 2 or raw_pkmsg[0] != 0x33:
            raise ValueError(f"Versión de PreKeySignalMessage inválida: {raw_pkmsg[:1].hex()}")

        pkmsg = PreKeySignalMessage()
        pkmsg.ParseFromString(raw_pkmsg[1:])

        dh1 = _dh(self.skey_priv_bytes, pkmsg.identity_key)
        dh2 = _dh(self.ident_priv_bytes, pkmsg.base_key)
        dh3 = _dh(self.skey_priv_bytes, pkmsg.base_key)
        master_secret = (b"\xff" * 32) + dh1 + dh2 + dh3

        if pkmsg.HasField("pre_key_id"):
            opk_priv = self.prekeys.get_private_key(pkmsg.pre_key_id)
            if opk_priv:
                master_secret += _dh(opk_priv, pkmsg.base_key)

        derived = _hkdf_sha256(master_secret, salt=b"\x00" * 32, info=b"WhisperText", length=64)
        session = {
            "remote_identity": _b64e(_strip_key_prefix(pkmsg.identity_key)),
            "root_key": _b64e(derived[:32]),
            "remote_ratchet": None,
            "local_ratchet_priv": None,
            "local_ratchet_pub": None,
            "recv_chain_key": None,
            "recv_counter": 0,
            "send_chain_key": None,
            "send_counter": 0,
            "previous_counter": 0,
        }

        return self._decrypt_signal_message(jid, pkmsg.message, session)

    def decrypt_msg(self, jid: str, raw_msg: bytes) -> bytes:
        session = self.sessions.get(jid)
        if not session:
            raise ValueError(f"No hay sesión Signal guardada para {jid}")
        return self._decrypt_signal_message(jid, raw_msg, session)

    def encrypt_msg(self, jid: str, plaintext_proto: bytes) -> bytes:
        session = self.sessions.get(jid)
        if not session or not session.get("remote_identity") or not session.get("remote_ratchet"):
            raise ValueError(
                f"No hay sesión Signal completa para {jid}. "
                "Primero debe llegar un mensaje de ese contacto."
            )

        root_key = _b64d(session["root_key"])
        remote_ratchet = _b64d(session["remote_ratchet"])
        remote_identity = _b64d(session["remote_identity"])

        if not session.get("send_chain_key"):
            _, local_priv, local_pub = generate_x25519_keypair()
            dh_out = _dh(local_priv, remote_ratchet)
            derived = _hkdf_sha256(dh_out, salt=root_key, info=b"WhisperRatchet", length=64)
            root_key = derived[:32]
            send_chain_key = derived[32:64]
            send_counter = 0
            session["root_key"] = _b64e(root_key)
            session["local_ratchet_priv"] = _b64e(local_priv)
            session["local_ratchet_pub"] = _b64e(local_pub)
        else:
            local_pub = _b64d(session["local_ratchet_pub"])
            send_chain_key = _b64d(session["send_chain_key"])
            send_counter = int(session.get("send_counter", 0))

        msg_key_seed = _hmac_sha256(send_chain_key, b"\x01")
        next_send_chain_key = _hmac_sha256(send_chain_key, b"\x02")

        keys = _hkdf_sha256(msg_key_seed, salt=b"\x00" * 32, info=b"WhisperMessageKeys", length=80)
        cipher_key = keys[0:32]
        mac_key = keys[32:64]
        iv = keys[64:80]

        padded_wa = _pad_wa_plaintext(plaintext_proto)
        ciphertext = _aes_cbc_encrypt(cipher_key, iv, padded_wa)

        sig_msg = SignalMessage()
        sig_msg.ratchet_key = _add_key_prefix(local_pub)
        sig_msg.counter = send_counter
        sig_msg.previous_counter = int(session.get("previous_counter", 0))
        sig_msg.ciphertext = ciphertext
        body = sig_msg.SerializeToString()

        mac_input = (
            _add_key_prefix(self.ident_pub_bytes)
            + _add_key_prefix(remote_identity)
            + b"\x33"
            + body
        )
        mac = _hmac_sha256(mac_key, mac_input)[:8]

        session["send_chain_key"] = _b64e(next_send_chain_key)
        session["send_counter"] = send_counter + 1
        self.sessions[jid] = session
        self._save_sessions()

        return b"\x33" + body + mac