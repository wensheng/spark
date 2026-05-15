"""Pure-Python RSA public-key signature verification.

Used by the Source Authority for validating signed loadable sources.
No external dependencies — works with the standard library only.
"""

from __future__ import annotations

import array
import base64
import hashlib
from functools import reduce


def key_factors(public_key_pem: str) -> tuple[int, int]:
    """Extract (modulus, public_exponent) from a PEM-encoded RSA public key."""
    key_start = "-----BEGIN PUBLIC KEY-----"
    key_end = "-----END PUBLIC KEY-----"
    key_start_p = public_key_pem.find(key_start) + len(key_start)
    key_end_p = public_key_pem.find(key_end, key_start_p)
    key_str = "".join(public_key_pem[key_start_p:key_end_p].strip().split("\n"))
    key_binary = list(base64.decodebytes(key_str.encode("ascii")))
    key_info, _ = _asn_decode(key_binary)
    return key_info[1][0]  # (modN, e)


# ---------------------------------------------------------------------------
# ASN.1 DER decoding (minimal — just enough for RSA public keys)
# ---------------------------------------------------------------------------


def _asn_decode(seq: list[int]) -> tuple:
    item_id = seq[0]
    item_len, rem_seq = _asn_decode_item_len(seq[1:])
    decoder = {
        0x02: _asn_decode_integer,
        0x03: _asn_decode_bitstring,
        0x05: _asn_decode_null,
        0x06: _asn_decode_object_id,
        0x30: _asn_decode_seq,
    }[item_id]
    return decoder(rem_seq, item_len)


def _asn_decode_item_len(seq: list[int]) -> tuple[int, list[int]]:
    seq_len = seq[0]
    seq_len_len = 0
    if seq_len & 0x80:
        seq_len_len = seq_len & 0x7F
        seq_len = _seq_to_int(seq[1:], seq_len_len)
    return seq_len, seq[1 + seq_len_len :]


def _seq_to_int(seq: list[int], int_len: int) -> int:
    return reduce(lambda a, b: (a << 8) + b, seq[:int_len])


def _asn_decode_integer(seq: list[int], seq_len: int) -> tuple[int, list[int]]:
    intval = _seq_to_int(seq, seq_len)
    if seq[0] & 0x80:
        intval = -intval
    return intval, seq[seq_len:]


def _asn_decode_bitstring(seq: list[int], seq_len: int) -> tuple:
    return _asn_decode_seq(seq[1:], seq_len - 1)


def _asn_decode_null(seq: list[int], seq_len: int) -> tuple[None, list[int]]:
    return None, seq


def _asn_decode_seq(seq: list[int], seq_len: int) -> tuple[list, list[int]]:
    rem = seq[:seq_len]
    seq_data: list = []
    while rem:
        data, rem = _asn_decode(rem)
        seq_data.append(data)
    return seq_data, seq[seq_len:]


def _asn_decode_object_id(seq: list[int], id_len: int) -> tuple[list[int], list[int]]:
    return seq[:id_len], seq[id_len:]


def _int_to_seq(intval: int, seqlen: int) -> list[int]:
    seq: list[int] = []
    while intval:
        seq.insert(0, intval & 0xFF)
        intval >>= 8
    return [0] * (seqlen - len(seq)) + seq


# PKCS#1 v1.5 SHA-256 signature prefix
_RSA_SIG_PREFIX = [
    0x30,
    0x31,
    0x30,
    0x0D,
    6,
    9,
    0x60,
    0x86,
    0x48,
    1,
    0x65,
    3,
    4,
    2,
    1,
    5,
    0,
    4,
    0x20,
]


def verify(
    message: list[int],
    signature: list[int],
    mod_n: int,
    e: int,
    hashfunc: type[hashlib._Hash] = hashlib.sha256,
) -> bool:
    """Verify an RSA signature over *message* using public key (mod_n, e)."""
    chash = hashfunc(list_to_bytes(message)).digest()
    int_sig = _seq_to_int(signature, len(signature))
    sig_factor = pow(int_sig, e, mod_n)
    s_check = _int_to_seq(sig_factor, len(signature))
    try:
        idx = s_check.index(0, 2)
        return s_check[:2] == [0, 1] and s_check[idx + 1 :] == (_RSA_SIG_PREFIX + list(chash))
    except (ValueError, IndexError):
        return False


def list_to_bytes(lst: list[int]) -> bytes:
    """Convert a list of ints to a bytes object."""
    return array.array("B", lst).tobytes()


def extract_ascii(inp_data: bytes, max_len: int) -> tuple[str, bytes]:
    """Extract a leading ASCII header from binary data."""
    for cpos in range(1, max_len):
        try:
            inp_data[:cpos].decode("ascii")
        except UnicodeDecodeError:
            return inp_data[: cpos - 1].decode("ascii"), inp_data[cpos:]
    return inp_data[:max_len].decode("ascii"), inp_data[max_len:]
