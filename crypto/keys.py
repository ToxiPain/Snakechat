# Generación de claves X25519 y firma XEdDSA (Signal/WhatsApp Curve25519)
import hashlib
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

_P = (1 << 255) - 19
_L = (1 << 252) + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P

_BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_BY = 46316835694926478169428394003475163141307993866256225615783033603165251855960
_BASE = (_BX, _BY, 1, (_BX * _BY) % _P)
_IDENTITY = (0, 1, 1, 0)

def _point_add(
    p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    a = ((p1[1] - p1[0]) * (p2[1] - p2[0])) % _P
    b = ((p1[1] + p1[0]) * (p2[1] + p2[0])) % _P
    c = (2 * p1[3] * p2[3] * _D) % _P
    d = (2 * p1[2] * p2[2]) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return ((e * f) % _P, (g * h) % _P, (f * g) % _P, (e * h) % _P)

def _scalar_mult(s: int, point: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    res = _IDENTITY
    addend = point
    while s > 0:
        if s & 1:
            res = _point_add(res, addend)
        addend = _point_add(addend, addend)
        s >>= 1
    return res

def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    zinv = pow(point[2], _P - 2, _P)
    x = (point[0] * zinv) % _P
    y = (point[1] * zinv) % _P
    out = bytearray(y.to_bytes(32, "little"))
    out[31] |= (x & 1) << 7
    return bytes(out)

def generate_x25519_keypair() -> tuple[x25519.X25519PrivateKey, bytes, bytes]:
    priv = x25519.X25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, priv_bytes, pub_bytes

def xeddsa_sign(private_key_bytes: bytes, message: bytes) -> bytes:
    k = bytearray(private_key_bytes)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    a = int.from_bytes(k, "little")

    e_point = _scalar_mult(a, _BASE)
    zinv = pow(e_point[2], _P - 2, _P)
    ex = (e_point[0] * zinv) % _P
    ey = (e_point[1] * zinv) % _P

    if ex & 1:
        a = (-a) % _L
    else:
        a = a % _L

    a_pub_bytes = ey.to_bytes(32, "little")
    a_priv_bytes = a.to_bytes(32, "little")

    nonce_z = os.urandom(64)
    prefix = b"\xfe" + b"\xff" * 31
    r = int.from_bytes(
        hashlib.sha512(prefix + a_priv_bytes + message + nonce_z).digest(), "little"
    ) % _L

    r_point = _scalar_mult(r, _BASE)
    r_bytes = _encode_point(r_point)

    h = int.from_bytes(
        hashlib.sha512(r_bytes + a_pub_bytes + message).digest(), "little"
    ) % _L
    s = (r + h * a) % _L

    return r_bytes + s.to_bytes(32, "little")
