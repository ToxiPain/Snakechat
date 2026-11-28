# Serialización y deserialización del protocolo binario de WhatsApp (WABinary)
from dataclasses import dataclass, field
from typing import Any
from binary.tokens import DOUBLE_BYTE_TOKENS, SINGLE_BYTE_TOKENS

TAGS = {
    "LIST_EMPTY": 0,
    "DICTIONARY_0": 236,
    "DICTIONARY_1": 237,
    "DICTIONARY_2": 238,
    "DICTIONARY_3": 239,
    "AD_JID": 247,
    "LIST_8": 248,
    "LIST_16": 249,
    "JID_PAIR": 250,
    "HEX_8": 251,
    "BINARY_8": 252,
    "BINARY_20": 253,
    "BINARY_32": 254,
    "NIBBLE_8": 255,
}

SINGLE_TOKEN_MAP = {tok: i for i, tok in enumerate(SINGLE_BYTE_TOKENS) if tok}
DOUBLE_TOKEN_MAP: dict[str, tuple[int, int]] = {}
for dict_idx, table in enumerate(DOUBLE_BYTE_TOKENS):
    for tok_idx, tok in enumerate(table):
        if tok and tok not in DOUBLE_TOKEN_MAP:
            DOUBLE_TOKEN_MAP[tok] = (dict_idx, tok_idx)

@dataclass
class BinaryNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    content: Any = None

    def get_child(self, tag: str) -> "BinaryNode | None":
        if isinstance(self.content, list):
            for child in self.content:
                if isinstance(child, BinaryNode) and child.tag == tag:
                    return child
        return None

    def get_children(self, tag: str) -> list["BinaryNode"]:
        if isinstance(self.content, list):
            return [c for c in self.content if isinstance(c, BinaryNode) and c.tag == tag]
        return []

    def __repr__(self) -> str:
        attrs_str = " ".join(f'{k}="{v}"' for k, v in self.attrs.items())
        header = f"<{self.tag} {attrs_str}>" if attrs_str else f"<{self.tag}>"
        if self.content is None:
            return header[:-1] + "/>"
        if isinstance(self.content, list):
            inner = ", ".join(repr(c) for c in self.content)
            return f"{header}[{inner}]</{self.tag}>"
        if isinstance(self.content, bytes):
            try:
                text = self.content.decode("utf-8")
                if len(text) > 40:
                    text = text[:40] + "..."
                return f"{header}{text!r}</{self.tag}>"
            except UnicodeDecodeError:
                return f"{header}<{len(self.content)} bytes></{self.tag}>"
        return f"{header}{self.content!r}</{self.tag}>"

class _Decoder:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bytes(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def read_int(self, n: int) -> int:
        return int.from_bytes(self.read_bytes(n), "big")

    def read_int20(self) -> int:
        b0, b1, b2 = self.read_byte(), self.read_byte(), self.read_byte()
        return ((b0 & 0x0F) << 16) | (b1 << 8) | b2

    def read_packed8(self, tag: int) -> str:
        start_byte = self.read_byte()
        length = start_byte & 127
        is_odd = bool(start_byte & 128)
        raw = self.read_bytes(length)

        chars = []
        for b in raw:
            for nib in ((b >> 4) & 0x0F, b & 0x0F):
                if tag == TAGS["NIBBLE_8"]:
                    if 0 <= nib <= 9:
                        chars.append(chr(48 + nib))
                    elif nib == 10:
                        chars.append("-")
                    elif nib == 11:
                        chars.append(".")
                    elif nib == 15:
                        chars.append("\x00")
                else:
                    if 0 <= nib <= 9:
                        chars.append(chr(48 + nib))
                    elif 10 <= nib <= 15:
                        chars.append(chr(65 + nib - 10))
        if is_odd and chars:
            chars.pop()
        return "".join(c for c in chars if c != "\x00")

    def read_list_size(self, tag: int) -> int:
        if tag == TAGS["LIST_EMPTY"]:
            return 0
        if tag == TAGS["LIST_8"]:
            return self.read_byte()
        if tag == TAGS["LIST_16"]:
            return self.read_int(2)
        raise ValueError(f"Tag de lista inválido: {tag}")

    def read_string_from_tag(self, tag: int) -> str:
        if 1 <= tag < len(SINGLE_BYTE_TOKENS):
            return SINGLE_BYTE_TOKENS[tag]
        if TAGS["DICTIONARY_0"] <= tag <= TAGS["DICTIONARY_3"]:
            dict_idx = tag - TAGS["DICTIONARY_0"]
            tok_idx = self.read_byte()
            return DOUBLE_BYTE_TOKENS[dict_idx][tok_idx]
        if tag == TAGS["LIST_EMPTY"]:
            return ""
        if tag == TAGS["BINARY_8"]:
            return self.read_bytes(self.read_byte()).decode("utf-8", errors="replace")
        if tag == TAGS["BINARY_20"]:
            return self.read_bytes(self.read_int20()).decode("utf-8", errors="replace")
        if tag == TAGS["BINARY_32"]:
            return self.read_bytes(self.read_int(4)).decode("utf-8", errors="replace")
        if tag == TAGS["JID_PAIR"]:
            user = self.read_string_from_tag(self.read_byte())
            server = self.read_string_from_tag(self.read_byte())
            return f"{user}@{server}" if user else server
        if tag == TAGS["AD_JID"]:
            domain_type = self.read_byte()
            device = self.read_byte()
            user = self.read_string_from_tag(self.read_byte())
            domain = "lid" if domain_type == 1 else "s.whatsapp.net"
            return f"{user}:{device}@{domain}" if device else f"{user}@{domain}"
        if tag in (TAGS["NIBBLE_8"], TAGS["HEX_8"]):
            return self.read_packed8(tag)
        raise ValueError(f"Tag de string desconocido: {tag}")

    def read_node(self) -> BinaryNode:
        list_size = self.read_list_size(self.read_byte())
        if list_size == 0:
            raise ValueError("Nodo vacío inválido")

        tag = self.read_string_from_tag(self.read_byte())
        attrs: dict[str, str] = {}
        num_attrs = (list_size - 1) >> 1
        for _ in range(num_attrs):
            key = self.read_string_from_tag(self.read_byte())
            val = self.read_string_from_tag(self.read_byte())
            attrs[key] = val

        content: Any = None
        if list_size % 2 == 0:
            content_tag = self.read_byte()
            if content_tag in (TAGS["LIST_EMPTY"], TAGS["LIST_8"], TAGS["LIST_16"]):
                child_count = self.read_list_size(content_tag)
                content = [self.read_node() for _ in range(child_count)]
            elif content_tag == TAGS["BINARY_8"]:
                content = self.read_bytes(self.read_byte())
            elif content_tag == TAGS["BINARY_20"]:
                content = self.read_bytes(self.read_int20())
            elif content_tag == TAGS["BINARY_32"]:
                content = self.read_bytes(self.read_int(4))
            else:
                content = self.read_string_from_tag(content_tag)

        return BinaryNode(tag=tag, attrs=attrs, content=content)

def decode_binary_node(data: bytes) -> BinaryNode:
    return _Decoder(data).read_node()

class _Encoder:
    def __init__(self):
        self.buf = bytearray()

    def write_byte(self, b: int):
        self.buf.append(b & 0xFF)

    def write_bytes(self, data: bytes):
        length = len(data)
        if length < 256:
            self.write_byte(TAGS["BINARY_8"])
            self.write_byte(length)
        elif length < (1 << 20):
            self.write_byte(TAGS["BINARY_20"])
            self.write_byte((length >> 16) & 0x0F)
            self.write_byte((length >> 8) & 0xFF)
            self.write_byte(length & 0xFF)
        else:
            self.write_byte(TAGS["BINARY_32"])
            self.buf.extend(length.to_bytes(4, "big"))
        self.buf.extend(data)

    def write_string(self, s: str):
        if s in SINGLE_TOKEN_MAP:
            self.write_byte(SINGLE_TOKEN_MAP[s])
            return
        if s in DOUBLE_TOKEN_MAP:
            dict_idx, tok_idx = DOUBLE_TOKEN_MAP[s]
            self.write_byte(TAGS["DICTIONARY_0"] + dict_idx)
            self.write_byte(tok_idx)
            return
        if "@" in s:
            user, server = s.split("@", 1)
            if ":" in user and server in ("s.whatsapp.net", "lid"):
                base_user, dev_str = user.split(":", 1)
                if dev_str.isdigit():
                    domain_type = 1 if server == "lid" else 0
                    self.write_byte(TAGS["AD_JID"])
                    self.write_byte(domain_type)
                    self.write_byte(int(dev_str))
                    self.write_string(base_user)
                    return

            self.write_byte(TAGS["JID_PAIR"])
            if user:
                self.write_string(user)
            else:
                self.write_byte(TAGS["LIST_EMPTY"])
            self.write_string(server)
            return
        self.write_bytes(s.encode("utf-8"))

    def write_list_start(self, length: int):
        if length == 0:
            self.write_byte(TAGS["LIST_EMPTY"])
        elif length < 256:
            self.write_byte(TAGS["LIST_8"])
            self.write_byte(length)
        else:
            self.write_byte(TAGS["LIST_16"])
            self.buf.extend(length.to_bytes(2, "big"))

    def write_node(self, node: BinaryNode):
        has_content = node.content is not None
        list_size = 1 + (2 * len(node.attrs)) + (1 if has_content else 0)
        self.write_list_start(list_size)
        self.write_string(node.tag)

        for k, v in node.attrs.items():
            self.write_string(k)
            self.write_string(str(v))

        if has_content:
            if isinstance(node.content, bytes):
                self.write_bytes(node.content)
            elif isinstance(node.content, str):
                self.write_string(node.content)
            elif isinstance(node.content, list):
                self.write_list_start(len(node.content))
                for child in node.content:
                    self.write_node(child)

def encode_binary_node(node: BinaryNode) -> bytes:
    enc = _Encoder()
    enc.write_node(node)
    return bytes(enc.buf)
