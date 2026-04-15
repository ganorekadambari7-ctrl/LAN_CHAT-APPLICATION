"""
AES-256 End-to-End Encryption Utility
Uses AES-GCM (authenticated encryption) — tamper-proof + confidential.
A shared passphrase is turned into a key via PBKDF2.
"""

import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_key(passphrase: str, salt: bytes = None):
    """Derive a 256-bit AES key from a passphrase using PBKDF2."""
    if salt is None:
        salt = b'lanchat_static_salt_v3'   # fixed salt so all clients derive same key
    key = hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, iterations=100_000)
    return key  # 32 bytes


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt a string. Returns base64-encoded nonce+ciphertext."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)   # 96-bit nonce
    ct = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(nonce + ct).decode('utf-8')


def decrypt(token: str, key: bytes) -> str:
    """Decrypt a base64-encoded token. Returns plaintext or raises ValueError."""
    try:
        data = base64.b64decode(token.encode('utf-8'))
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode('utf-8')
    except Exception:
        raise ValueError('Decryption failed — wrong passphrase or tampered message.')
