import base64

from cryptography.hazmat.primitives.asymmetric import padding, rsa

from bot.utils.happ_crypto import (
    HAPP_CRYPT4_PREFIX,
    _encrypt_rsa_pkcs1_v15,
    _happ_crypt4_public_key,
    create_happ_crypt4_link,
)


def test_rsa_helper_uses_pkcs1_v15_padding() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    plaintext = b"https://subscription.example.test/s/test"

    ciphertext = _encrypt_rsa_pkcs1_v15(plaintext, private_key.public_key())

    assert private_key.decrypt(ciphertext, padding.PKCS1v15()) == plaintext


def test_happ_crypt4_link_uses_published_4096_bit_key() -> None:
    link = create_happ_crypt4_link("https://subscription.example.test/s/test")

    assert link is not None
    assert link.startswith(HAPP_CRYPT4_PREFIX)
    ciphertext = base64.b64decode(link.removeprefix(HAPP_CRYPT4_PREFIX), validate=True)
    assert len(ciphertext) == 512


def test_happ_crypt4_rejects_content_above_pkcs1_limit() -> None:
    assert create_happ_crypt4_link("x" * 502) is None


def test_happ_crypt4_public_key_is_valid_pem() -> None:
    public_key = _happ_crypt4_public_key()

    assert public_key.key_size == 4096
    assert public_key.public_numbers().e == 65537
