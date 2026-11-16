"""RFC 6238 TOTP (SHA-1, 6 digits, 30 s), standard-library only."""
import base64, hmac, struct, time


def code(secret: str, counter: int) -> str:
    h = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), "sha1").digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def verify(secret: str, given: str, last: int):
    """Return the matched time-step (store it as `last` to block replays) or None."""
    now = int(time.time() // 30)
    for c in (now - 1, now, now + 1):
        if c > last and hmac.compare_digest(code(secret, c), given):
            return c
    return None
