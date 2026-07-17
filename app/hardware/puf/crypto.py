"""Purpose: Provide deterministic cryptographic primitives for PUF simulation and template protection.
Directory: app/hardware/puf.
Dependencies: hashlib, hmac, json, math, secrets.
Connection: Simulator derives process variation; verifier seals references and signs enrollment profiles.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
from dataclasses import dataclass
from typing import Any

from app.hardware.puf.exceptions import PUFIntegrityError


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def hmac_sha256(key: bytes, *parts: bytes | str) -> bytes:
    digest = hmac.new(key, digestmod=hashlib.sha256)
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def hmac_hex(key: bytes, *parts: bytes | str) -> str:
    return hmac_sha256(key, *parts).hex()


def derive_key(master_key: bytes, label: str, length: int = 32) -> bytes:
    if len(master_key) < 32:
        raise ValueError("master key must contain at least 32 bytes")
    if length <= 0:
        raise ValueError("derived key length must be positive")
    output = bytearray()
    counter = 1
    previous = b""
    while len(output) < length:
        previous = hmac_sha256(master_key, previous, label, counter.to_bytes(4, "big"))
        output.extend(previous)
        counter += 1
    return bytes(output[:length])


def bits_to_bytes(bits: str) -> bytes:
    if any(bit not in "01" for bit in bits):
        raise ValueError("bit string may only contain 0 and 1")
    length = len(bits)
    padded = bits + ("0" * ((8 - length % 8) % 8))
    payload = bytes(int(padded[index : index + 8], 2) for index in range(0, len(padded), 8))
    return length.to_bytes(4, "big") + payload


def bytes_to_bits(payload: bytes) -> str:
    if len(payload) < 4:
        raise ValueError("encoded bit string is too short")
    length = int.from_bytes(payload[:4], "big")
    bits = "".join(f"{item:08b}" for item in payload[4:])
    if length > len(bits):
        raise ValueError("encoded bit length exceeds payload")
    return bits[:length]


def xor_bytes(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("xor operands must have identical length")
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _keystream(key: bytes, context: bytes, length: int) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream.extend(hmac_sha256(key, b"puf-template-stream", context, counter.to_bytes(8, "big")))
        counter += 1
    return bytes(stream[:length])


def seal_bytes(key: bytes, plaintext: bytes, context: bytes) -> tuple[str, str]:
    nonce = secrets.token_bytes(16)
    stream = _keystream(key, nonce + context, len(plaintext))
    ciphertext = xor_bytes(plaintext, stream)
    envelope = nonce + ciphertext
    tag = hmac_sha256(key, b"puf-template-tag", context, envelope)
    return envelope.hex(), tag.hex()


def unseal_bytes(key: bytes, sealed_hex: str, tag_hex: str, context: bytes) -> bytes:
    try:
        envelope = bytes.fromhex(sealed_hex)
        supplied_tag = bytes.fromhex(tag_hex)
    except ValueError as exc:
        raise PUFIntegrityError("PUF template encoding is invalid") from exc
    expected_tag = hmac_sha256(key, b"puf-template-tag", context, envelope)
    if not hmac.compare_digest(expected_tag, supplied_tag):
        raise PUFIntegrityError("PUF template authentication tag is invalid")
    if len(envelope) < 16:
        raise PUFIntegrityError("PUF template envelope is truncated")
    nonce, ciphertext = envelope[:16], envelope[16:]
    stream = _keystream(key, nonce + context, len(ciphertext))
    return xor_bytes(ciphertext, stream)


@dataclass(slots=True)
class DeterministicPRNG:
    """HMAC counter-mode deterministic random source with Box-Muller Gaussian output."""

    key: bytes
    context: bytes
    _counter: int = 0
    _buffer: bytes = b""
    _spare_normal: float | None = None

    def _refill(self) -> None:
        self._buffer += hmac_sha256(
            self.key,
            b"puf-prng",
            self.context,
            self._counter.to_bytes(8, "big"),
        )
        self._counter += 1

    def bytes(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length cannot be negative")
        while len(self._buffer) < length:
            self._refill()
        result, self._buffer = self._buffer[:length], self._buffer[length:]
        return result

    def random(self) -> float:
        integer = int.from_bytes(self.bytes(8), "big") >> 11
        return integer / float(1 << 53)

    def uniform(self, minimum: float, maximum: float) -> float:
        if maximum < minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        return minimum + (maximum - minimum) * self.random()

    def normal(self, mean: float = 0.0, standard_deviation: float = 1.0) -> float:
        if standard_deviation < 0:
            raise ValueError("standard deviation cannot be negative")
        if self._spare_normal is not None:
            value = self._spare_normal
            self._spare_normal = None
            return mean + standard_deviation * value
        u1 = max(self.random(), 1e-15)
        u2 = self.random()
        radius = math.sqrt(-2.0 * math.log(u1))
        angle = 2.0 * math.pi * u2
        first = radius * math.cos(angle)
        self._spare_normal = radius * math.sin(angle)
        return mean + standard_deviation * first

    def randint(self, minimum: int, maximum: int) -> int:
        if maximum < minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        span = maximum - minimum + 1
        limit = (1 << 64) - ((1 << 64) % span)
        while True:
            value = int.from_bytes(self.bytes(8), "big")
            if value < limit:
                return minimum + value % span

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            target = self.randint(0, index)
            values[index], values[target] = values[target], values[index]
