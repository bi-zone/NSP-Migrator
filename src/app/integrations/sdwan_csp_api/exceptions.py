class SDWANCspHttpError(Exception):
    """Base exception for SD-WAN CSP API integration."""


class SDWANCspHttpAuthError(SDWANCspHttpError):
    """Authentication or authorization error."""


class SDWANCspHttpConnectionError(SDWANCspHttpError):
    """Network/connectivity/timeout error while calling SD-WAN CSP API."""


class SDWANCspHttpResponseError(SDWANCspHttpError):
    """Unexpected or invalid response received from SD-WAN CSP API."""
