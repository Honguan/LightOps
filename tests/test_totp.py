from cryptography.fernet import Fernet

from lightops.security import decrypt_secret, encrypt_secret, totp_code, verify_totp


def test_totp_matches_rfc_6238_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    assert totp_code(secret, timestamp=59) == "287082"
    assert verify_totp(secret, "287082", timestamp=59)
    assert not verify_totp(secret, "000000", timestamp=59)


def test_sensitive_totp_secret_is_encrypted_at_rest() -> None:
    key = Fernet.generate_key()
    encrypted = encrypt_secret("top-secret", key)

    assert "top-secret" not in encrypted
    assert decrypt_secret(encrypted, key) == "top-secret"
