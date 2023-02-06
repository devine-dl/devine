import ssl
from typing import Optional

from requests.adapters import HTTPAdapter


class SSLCiphers(HTTPAdapter):
    """
    Custom HTTP Adapter to change the TLS Cipher set and security requirements.

    Security Level may optionally be provided. A level above 0 must be used at all times.
    A list of Security Levels and their security is listed below. Usually 2 is used by default.
    Do not set the Security level via @SECLEVEL in the cipher list.

    Level 0:
        Everything is permitted. This retains compatibility with previous versions of OpenSSL.

    Level 1:
        The security level corresponds to a minimum of 80 bits of security. Any parameters
        offering below 80 bits of security are excluded. As a result RSA, DSA and DH keys
        shorter than 1024 bits and ECC keys shorter than 160 bits are prohibited. All export
        cipher suites are prohibited since they all offer less than 80 bits of security. SSL
        version 2 is prohibited. Any cipher suite using MD5 for the MAC is also prohibited.

    Level 2:
        Security level set to 112 bits of security. As a result RSA, DSA and DH keys shorter
        than 2048 bits and ECC keys shorter than 224 bits are prohibited. In addition to the
        level 1 exclusions any cipher suite using RC4 is also prohibited. SSL version 3 is
        also not allowed. Compression is disabled.

    Level 3:
        Security level set to 128 bits of security. As a result RSA, DSA and DH keys shorter
        than 3072 bits and ECC keys shorter than 256 bits are prohibited. In addition to the
        level 2 exclusions cipher suites not offering forward secrecy are prohibited. TLS
        versions below 1.1 are not permitted. Session tickets are disabled.

    Level 4:
        Security level set to 192 bits of security. As a result RSA, DSA and DH keys shorter
        than 7680 bits and ECC keys shorter than 384 bits are prohibited. Cipher suites using
        SHA1 for the MAC are prohibited. TLS versions below 1.2 are not permitted.

    Level 5:
        Security level set to 256 bits of security. As a result RSA, DSA and DH keys shorter
        than 15360 bits and ECC keys shorter than 512 bits are prohibited.
    """

    def __init__(self, cipher_list: Optional[str] = None, security_level: int = 0, *args, **kwargs):
        if cipher_list:
            if not isinstance(cipher_list, str):
                raise TypeError(f"Expected cipher_list to be a str, not {cipher_list!r}")
            if "@SECLEVEL" in cipher_list:
                raise ValueError("You must not specify the Security Level manually in the cipher list.")
        if not isinstance(security_level, int):
            raise TypeError(f"Expected security_level to be an int, not {security_level!r}")
        if security_level not in range(6):
            raise ValueError(f"The security_level must be a value between 0 and 5, not {security_level}")

        if not cipher_list:
            # cpython's default cipher list differs to Python-requests cipher list
            cipher_list = "DEFAULT"

        cipher_list += f":@SECLEVEL={security_level}"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # For some reason this is needed to avoid a verification error
        ctx.set_ciphers(cipher_list)

        self._ssl_context = ctx
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().proxy_manager_for(*args, **kwargs)
