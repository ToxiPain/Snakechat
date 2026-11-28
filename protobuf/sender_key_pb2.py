# Clases proto manuales para Sender Key (grupos WhatsApp)
# Compatible con libsignal / Baileys / Whatsmeow.
#
# SenderKeyMessage (enc type="skmsg"):
#   byte 0        : versión (0x33 = v3)
#   bytes 1..N-64 : proto serializado
#       field 1 (uint32): id         -> chain_id
#       field 2 (uint32): iteration  -> iteración actual de la cadena
#       field 3 (bytes) : ciphertext -> texto cifrado AES-256-CBC
#   bytes N-64..N : firma XEdDSA (64 bytes)
#
# SenderKeyDistributionMessage (dentro de WAMessage.sender_key_distribution_message):
#   byte 0        : versión (0x33 = v3)
#   bytes 1..N    : proto serializado
#       field 1 (uint32): id          -> chain_id
#       field 2 (uint32): iteration   -> iteración inicial
#       field 3 (bytes) : chain_key   -> 32 bytes de cadena inicial
#       field 4 (bytes) : signing_key -> clave pública del firmante (33 bytes con 0x05)

import struct


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("Buffer terminó leyendo varint")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return result, pos


def _parse_proto_fields(data: bytes) -> dict:
    fields: dict = {}
    pos = 0
    while pos < len(data):
        tag_val, pos = _read_varint(data, pos)
        field_num = tag_val >> 3
        wire_type = tag_val & 0x07
        if wire_type == 0:
            val, pos = _read_varint(data, pos)
            fields[field_num] = val
        elif wire_type == 2:
            length, pos = _read_varint(data, pos)
            fields[field_num] = data[pos : pos + length]
            pos += length
        elif wire_type == 5:
            fields[field_num] = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        elif wire_type == 1:
            fields[field_num] = struct.unpack_from("<Q", data, pos)[0]
            pos += 8
        else:
            raise ValueError(f"Wire type {wire_type} no soportado en pos {pos}")
    return fields


class SenderKeyMessage:
    def __init__(self):
        self.id: int = 0
        self.iteration: int = 0
        self.ciphertext: bytes = b""

    def ParseFromString(self, data: bytes) -> None:
        fields = _parse_proto_fields(data)
        self.id = int(fields.get(1, 0))
        self.iteration = int(fields.get(2, 0))
        self.ciphertext = bytes(fields.get(3, b""))


class SenderKeyDistributionMessage:
    def __init__(self):
        self.id: int = 0
        self.iteration: int = 0
        self.chain_key: bytes = b""
        self.signing_key: bytes = b""

    def ParseFromString(self, data: bytes) -> None:
        # Quitar el byte de versión 0x33 si está presente
        if data and data[0] == 0x33:
            data = data[1:]
        fields = _parse_proto_fields(data)
        self.id = int(fields.get(1, 0))
        self.iteration = int(fields.get(2, 0))
        self.chain_key = bytes(fields.get(3, b""))
        self.signing_key = bytes(fields.get(4, b""))