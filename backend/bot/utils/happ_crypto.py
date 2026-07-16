import base64
import logging
from functools import lru_cache

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

HAPP_CRYPT4_PREFIX = "happ://crypt4/"

# Happ Crypt4 v4 public key published by @kastov/cryptohapp (MIT):
# https://github.com/kastov/cryptohapp/blob/main/src/constants/crypt4.constant.ts
_HAPP_CRYPT4_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA3UZ0M3L4K+WjM3vkbQnz
ozHg/cRbEXvQ6i4A8RVN4OM3rK9kU01FdjyoIgywve8OEKsFnVwERZAQZ1Trv60B
hmaM76QQEE+EUlIOL9EpwKWGtTL5lYC1sT9XJMNP3/CI0gP5wwQI88cY/xedpOEB
W72EmOOShHUm/b/3m+HPmqwc4ugKj5zWV5SyiT829aFA5DxSjmIIFBAms7DafmSq
LFTYIQL5cShDY2u+/sqyAw9yZIOoqW2TFIgIHhLPWek/ocDU7zyOrlu1E0SmcQQb
LFqHq02fsnH6IcqTv3N5Adb/CkZDDQ6HvQVBmqbKZKf7ZdXkqsc/Zw27xhG7OfXC
tUmWsiL7zA+KoTd3avyOh93Q9ju4UQsHthL3Gs4vECYOCS9dsXXSHEY/1ngU/hjO
WFF8QEE/rYV6nA4PTyUvo5RsctSQL/9DJX7XNh3zngvif8LsCN2MPvx6X+zLouBX
zgBkQ9DFfZAGLWf9TR7KVjZC/3NsuUCDoAOcpmN8pENBbeB0puiKMMWSvll36+2M
YR1Xs0MgT8Y9TwhE2+TnnTJOhzmHi/BxiUlY/w2E0s4ax9GHAmX0wyF4zeV7kDkc
vHuEdc0d7vDmdw0oqCqWj0Xwq86HfORu6tm1A8uRATjb4SzjTKclKuoElVAVa5Jo
oh/uZMozC65SmDw+N5p6Su8CAwEAAQ==
-----END PUBLIC KEY-----
"""


@lru_cache(maxsize=1)
def _happ_crypt4_public_key() -> rsa.RSAPublicKey:
    public_key = serialization.load_pem_public_key(_HAPP_CRYPT4_PUBLIC_KEY_PEM)
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise TypeError("Happ Crypt4 key is not an RSA public key.")
    return public_key


def _encrypt_rsa_pkcs1_v15(content: bytes, public_key: rsa.RSAPublicKey) -> bytes:
    return public_key.encrypt(content, padding.PKCS1v15())


def create_happ_crypt4_link(content: str) -> str | None:
    """Create a Happ Crypt4 deep link without depending on the panel API."""
    if not content:
        return None
    try:
        encrypted = _encrypt_rsa_pkcs1_v15(content.encode("utf-8"), _happ_crypt4_public_key())
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        logger.warning("Happ Crypt4 encryption failed: %s", exc)
        return None
    return HAPP_CRYPT4_PREFIX + base64.b64encode(encrypted).decode("ascii")
