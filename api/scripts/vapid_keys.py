"""Generate a VAPID key pair for browser push notifications.

    make vapid-keys

Prints VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY lines for api/.env, in the
format browsers and pywebpush expect: base64url without padding, the
public key an uncompressed P-256 point (65 bytes), the private key its
raw 32-byte scalar. Generate once per deployment and keep the pair:
changing it invalidates every browser's subscription.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(public), _b64url(private)


if __name__ == "__main__":
    public_key, private_key = generate()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("VAPID_SUBJECT=mailto:ops@yourdomain")
