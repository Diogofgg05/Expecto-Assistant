"""Domain-oriented dispatch for explicit user memory commands.

Model-generated output cannot authorize these handlers; AuraEngine invokes
this facade only for explicit user commands.
"""
from __future__ import annotations
from .policy import handle_policy_commands
from .relations import handle_relationship_commands
from .temporal import handle_temporal_commands
from .episodes import handle_episode_commands
from .notes import handle_note_commands

# The original matching precedence is a compatibility contract.
HANDLERS = (
    handle_policy_commands,
    handle_relationship_commands,
    handle_temporal_commands,
    handle_episode_commands,
    handle_note_commands,
)


async def handle_memory_command(engine, original: str, key: str, respond):
    """Return the first recognized command result, or None for fallthrough."""
    for handler in HANDLERS:
        result = await handler(engine, original, key, respond)
        if result is not None:
            return result
    return None


__all__ = ("handle_memory_command",)
