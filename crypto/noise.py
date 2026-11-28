# Túnel cifrado Noise: transporte activo tras completar el handshake XX
import struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class NoiseTransport:

    def __init__(self, write_key: bytes, read_key: bytes):
        self.write_cipher = AESGCM(write_key)
        self.read_cipher = AESGCM(read_key)
        self.write_counter = 0
        self.read_counter = 0

    def _make_iv(self, counter: int) -> bytes:
        return b"\x00" * 8 + struct.pack(">I", counter)

    def encrypt(self, plaintext: bytes) -> bytes:
        iv = self._make_iv(self.write_counter)
        self.write_counter += 1
        return self.write_cipher.encrypt(iv, plaintext, b"")

    def decrypt(self, ciphertext: bytes) -> bytes:
        iv = self._make_iv(self.read_counter)
        self.read_counter += 1
        return self.read_cipher.decrypt(iv, ciphertext, b"")
