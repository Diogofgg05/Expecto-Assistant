"""Local-first intent risk gate inspired by on-device processing and explicit consent."""
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

class Risk(str, Enum):
    LOCAL = "local"
    NETWORK = "network"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"

@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_confirmation: bool
    reason: str

class IntentPrivacyGate:
    """Default-deny external and destructive actions; no hidden cloud fallback.

    This gate evaluates *declared* action capabilities, not untrusted natural-language
    text. Adapters must declare their capabilities before execution.
    """
    VALID = frozenset({"local_read", "network", "sensitive_read", "write", "delete", "execute"})
    def __init__(self, *, network_enabled: bool = False):
        self.network_enabled = network_enabled

    def evaluate(self, capabilities: Iterable[str], *, confirmed: bool = False) -> Decision:
        requested = frozenset(capabilities)
        unknown = requested - self.VALID
        if unknown:
            return Decision(False, False, "unknown_capability")
        if "network" in requested and not self.network_enabled:
            return Decision(False, False, "network_disabled")
        risky = requested & {"sensitive_read", "write", "delete", "execute"}
        if risky and not confirmed:
            return Decision(False, True, "explicit_confirmation_required")
        return Decision(True, False, "allowed")
