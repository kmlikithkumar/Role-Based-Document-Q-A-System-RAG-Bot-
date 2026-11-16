import base64, hashlib, os

from cryptography.fernet import Fernet

MAGIC = b"RAGB1"


def _kdf(pw: str, salt: bytes) -> bytes:
    return base64.urlsafe_b64encode(hashlib.scrypt(pw.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=2**26))


def encrypt(data: bytes, pw: str) -> bytes:
    salt = os.urandom(16)
    return MAGIC + salt + Fernet(_kdf(pw, salt)).encrypt(data)


def decrypt(blob: bytes, pw: str) -> bytes:
    assert blob.startswith(MAGIC), "Not an encrypted backup."
    return Fernet(_kdf(pw, blob[5:21])).decrypt(blob[21:])


def _f(material: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def seal(text: str, material: str) -> str:
    return _f(material).encrypt(text.encode()).decode()


def unseal(token: str, material: str) -> str:
    return _f(material).decrypt(token.encode()).decode()
