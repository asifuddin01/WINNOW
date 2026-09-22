"""AES-256-GCM for secrets stored in the database (guide 12.7), e.g. TOTP secrets."""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12


def encrypt(key: bytes, plaintext: bytes, context: bytes) -> bytes:
    """Nonce + ciphertext. `context` (for example the owner's id) is authenticated, so a
    ciphertext copied onto another row fails to decrypt."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, context)


def decrypt(key: bytes, blob: bytes, context: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], context)
