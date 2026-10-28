"""Offline contract tests for cancellable voice orchestration."""
from aura.voice_turns import VoiceTurns, Phase

def test_turn_lifecycle():
    v = VoiceTurns(clock=lambda: 1.0)
    start = v.listen()
    assert start.kind == "cancel_previous"
    request = v.transcript("  Olá Expecto  ")
    assert request.kind == "request_llm" and request.text == "Olá Expecto"
    speak = v.answer(request.generation, "Bom dia")
    assert speak.kind == "request_tts" and v.phase == Phase.SPEAKING
    assert v.finished(request.generation).kind == "idle"

def test_barge_in_cancels_late_results():
    v = VoiceTurns()
    v.listen()
    old = v.transcript("primeira").generation
    v.listen()
    assert v.answer(old, "resposta atrasada").kind == "stale"
    new = v.transcript("segunda").generation
    assert new != old
    assert v.answer(new, "resposta nova").kind == "request_tts"
    assert v.finished(old).kind == "stale"

def test_stop_invalidates_all_work():
    v = VoiceTurns()
    v.listen()
    generation = v.transcript("olá").generation
    v.stop()
    assert v.answer(generation, "não reproduzir").kind == "stale"
    assert v.phase == Phase.IDLE

def test_rejects_empty_and_unexpected_transcripts():
    v = VoiceTurns()
    assert v.transcript("hey").kind == "ignored"
    v.listen()
    assert v.transcript("   ").kind == "ignored"
    assert v.phase == Phase.LISTENING

def test_text_is_bounded():
    v = VoiceTurns(max_text=4)
    v.listen()
    assert v.transcript("12345678").text == "1234"
    assert v.answer(v.generation, "abcdef").text == "abcd"

def test_elapsed_is_nonnegative():
    now = [3.0]
    v = VoiceTurns(clock=lambda: now[0])
    v.listen()
    now[0] = 3.25
    assert v.snapshot()["elapsed_ms"] == 250

def test_invalid_limits():
    import pytest
    with pytest.raises(ValueError):
        VoiceTurns(max_text=0)
