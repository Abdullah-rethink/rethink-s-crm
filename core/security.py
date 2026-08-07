import base64
import hashlib
import os

# Secret key derived from environment variable or local system secret
SECRET_SALT = os.environ.get("APP_SECRET_KEY", "RethinkCharityCRM_SecretKey_2026!").encode('utf-8')


def _get_key_bytes():
    return hashlib.sha256(SECRET_SALT).digest()


def encrypt_string(plain_text: str) -> str:
    """Encrypts a plaintext string into a base64 encoded payload."""
    if not plain_text:
        return ""
    key = _get_key_bytes()
    data = plain_text.encode('utf-8')
    # XOR cipher with SHA-256 key stream
    cipher_bytes = bytearray()
    for idx, byte in enumerate(data):
        cipher_bytes.append(byte ^ key[idx % len(key)])
    return "enc::" + base64.b64encode(bytes(cipher_bytes)).decode('utf-8')


def decrypt_string(cipher_text: str) -> str:
    """Decrypts a base64 encoded payload back into plaintext."""
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc::"):
        # Not encrypted yet (raw legacy password)
        return cipher_text
    try:
        raw_b64 = cipher_text[5:]
        data = base64.b64decode(raw_b64)
        key = _get_key_bytes()
        plain_bytes = bytearray()
        for idx, byte in enumerate(data):
            plain_bytes.append(byte ^ key[idx % len(key)])
        return plain_bytes.decode('utf-8')
    except Exception:
        return cipher_text
