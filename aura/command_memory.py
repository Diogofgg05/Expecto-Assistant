"""Compatibility entry point for deterministic memory commands.

Implementation is now grouped by domain under aura.memory_commands.
The public import path used by AuraEngine remains unchanged.
"""
from .memory_commands import handle_memory_command

__all__ = ("handle_memory_command",)
