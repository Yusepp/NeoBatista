"""Domain exceptions translated into friendly Discord responses."""


class NeoBatistaError(Exception):
    """Base exception for expected bot failures."""


class ConfigurationError(NeoBatistaError):
    """Raised when deployment configuration is invalid."""


class MediaResolutionError(NeoBatistaError):
    """Raised when a media query cannot be resolved."""


class PlayerError(NeoBatistaError):
    """Raised when a guild player cannot perform an operation."""


class QueuePositionError(PlayerError):
    """Raised when a one-based queue position is invalid."""
