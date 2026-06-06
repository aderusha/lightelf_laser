"""Exceptions for the LightElf Laser integration."""

from __future__ import annotations


class LightElfLaserError(Exception):
    """Raised when the laser rejects a command or cannot be reached."""
