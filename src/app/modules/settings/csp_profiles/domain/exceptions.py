class CSPProfileError(Exception):
    """Base class for typed CSP profile failures."""


class InvalidCSPProfileError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP profile is invalid")


class InvalidCertificateBundleError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("Certificate bundle is invalid")


class CSPProfileNotFoundError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP profile was not found")


class DuplicateCSPProfileNameError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP profile name already exists")


class CSPProfilePreconditionRequiredError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("If-Match header is required")


class CSPProfileRequiredError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("A stored CSP profile is required")


class CSPProfileConnectionValidationError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP profile cannot be used for connection")


class CSPProfileAuthenticationError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP authentication failed")


class CSPProfileConnectionError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("CSP connection test failed")


class CredentialEncryptionError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("Credential encryption failed")


class CredentialDecryptionError(CSPProfileError):
    def __init__(self) -> None:
        super().__init__("Credential decryption failed")


class CredentialIntegrityError(CredentialDecryptionError):
    def __init__(self) -> None:
        CSPProfileError.__init__(self, "Credential integrity verification failed")
