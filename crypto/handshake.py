# Handshake Noise XX: negociación de claves efímeras y estáticas con AES-GCM + SHA-256
import hashlib
import struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .noise import NoiseTransport

NOISE_PATTERN = b"Noise_XX_25519_AESGCM_SHA256\x00\x00\x00\x00"

class NoiseHandshakeState:

    def __init__(self):
        self.h = NOISE_PATTERN
        self.ck = NOISE_PATTERN
        self.key = NOISE_PATTERN
        self.counter = 0

    def mix_hash(self, data: bytes):
        self.h = hashlib.sha256(self.h + data).digest()

    def start(self, header: bytes):
        self.mix_hash(header)

    def authenticate(self, data: bytes):
        self.mix_hash(data)

    def _generate_iv(self) -> bytes:
        iv = b"\x00" * 8 + struct.pack(">I", self.counter)
        self.counter += 1
        return iv

    def mix_key(self, data: bytes):
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=self.ck,
            info=b"",
        )
        derived = hkdf.derive(data)
        self.ck = derived[:32]
        self.key = derived[32:]
        self.counter = 0

    def encrypt(self, plaintext: bytes) -> bytes:
        iv = self._generate_iv()
        ciphertext = AESGCM(self.key).encrypt(iv, plaintext, self.h)
        self.mix_hash(ciphertext)
        return ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        iv = self._generate_iv()
        plaintext = AESGCM(self.key).decrypt(iv, ciphertext, self.h)
        self.mix_hash(ciphertext)
        return plaintext

    def finish(self) -> NoiseTransport:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=self.ck,
            info=b"",
        )
        derived = hkdf.derive(b"")
        return NoiseTransport(write_key=derived[:32], read_key=derived[32:])
