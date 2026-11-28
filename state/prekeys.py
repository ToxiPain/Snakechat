# Almacén de pre-keys de un solo uso para el protocolo Signal
import base64
import json
import struct
from pathlib import Path

from crypto.keys import generate_x25519_keypair, xeddsa_sign
from binary import BinaryNode

PREKEYS_PATH = Path(__file__).resolve().parent / "prekeys.json"

def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))

class PreKeyStore:

    def __init__(self, store_path: Path = PREKEYS_PATH):
        self.store_path = store_path
        self.next_id: int = 1
        self.keys: dict[str, dict[str, str]] = {}

        if self.store_path.exists():
            self._load()

    def _load(self):
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.next_id = int(data.get("next_id", 1))
        self.keys = data.get("keys", {})

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_id": self.next_id,
            "keys": self.keys,
        }
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def generate_batch(self, count: int = 30) -> list[tuple[int, bytes]]:
        batch: list[tuple[int, bytes]] = []
        for _ in range(count):
            key_id = self.next_id
            self.next_id += 1
            _, priv_bytes, pub_bytes = generate_x25519_keypair()
            self.keys[str(key_id)] = {
                "priv": _b64e(priv_bytes),
                "pub": _b64e(pub_bytes),
            }
            batch.append((key_id, pub_bytes))
        self._save()
        print(f"[+] {count} Pre-Keys generadas y guardadas en {self.store_path}")
        return batch

    def get_private_key(self, key_id: int) -> bytes | None:
        entry = self.keys.get(str(key_id))
        return _b64d(entry["priv"]) if entry else None

    def build_upload_iq(
        self,
        iq_id: str,
        reg_id: int,
        ident_priv_bytes: bytes,
        ident_pub_bytes: bytes,
        skey_pub_bytes: bytes,
        count: int = 30,
    ) -> BinaryNode:
        batch = self.generate_batch(count)
        skey_sig = xeddsa_sign(ident_priv_bytes, b"\x05" + skey_pub_bytes)

        key_nodes = [
            BinaryNode(
                tag="key",
                content=[
                    BinaryNode(tag="id", content=struct.pack(">I", key_id)[1:]),
                    BinaryNode(tag="value", content=pub_bytes),
                ],
            )
            for key_id, pub_bytes in batch
        ]

        return BinaryNode(
            tag="iq",
            attrs={
                "id": iq_id,
                "xmlns": "encrypt",
                "type": "set",
                "to": "s.whatsapp.net",
            },
            content=[
                BinaryNode(tag="registration", content=struct.pack(">I", reg_id)),
                BinaryNode(tag="type", content=b"\x05"),
                BinaryNode(tag="identity", content=ident_pub_bytes),
                BinaryNode(tag="list", content=key_nodes),
                BinaryNode(
                    tag="skey",
                    content=[
                        BinaryNode(tag="id", content=struct.pack(">I", 1)[1:]),
                        BinaryNode(tag="value", content=skey_pub_bytes),
                        BinaryNode(tag="signature", content=skey_sig),
                    ],
                ),
            ],
        )
