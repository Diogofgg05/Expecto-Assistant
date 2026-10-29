from aura.intent_privacy import IntentPrivacyGate

def test_local_read_is_allowed():
    assert IntentPrivacyGate().evaluate(["local_read"]).allowed

def test_network_is_off_by_default():
    assert IntentPrivacyGate().evaluate(["network"], confirmed=True).reason == "network_disabled"

def test_network_opt_in():
    assert IntentPrivacyGate(network_enabled=True).evaluate(["network"]).allowed

def test_destructive_action_requires_confirmation():
    d = IntentPrivacyGate().evaluate(["delete"])
    assert not d.allowed and d.requires_confirmation
    assert IntentPrivacyGate().evaluate(["delete"], confirmed=True).allowed

def test_unknown_capabilities_fail_closed():
    assert not IntentPrivacyGate().evaluate(["superuser"]).allowed

def test_empty_capabilities_allowed():
    assert IntentPrivacyGate().evaluate([]).allowed

def test_sensitive_read_requires_confirmation():
    assert IntentPrivacyGate().evaluate(["sensitive_read"]).requires_confirmation
