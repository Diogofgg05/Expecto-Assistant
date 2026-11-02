"""Offline, deterministic evaluation of relevance-aware context packing."""
from aura.context_selection import Passage, pack_context, unranked_context
from aura.performance import PerformanceMonitor


def test_relevance_promotes_relevant_memory_despite_old_order():
    passages = [
        Passage("summary", "O utilizador gosta de receitas vegetarianas."),
        Passage("summary", "O projeto foi criado com arquitetura de plugins."),
        Passage("notes", "A cor preferida de referência é azul."),
        Passage("notes", "O EXPECTO funciona com modelo Ollama local.", importance=1),
        Passage("documents", "Manual do Ollama: a API chat aceita stream verdadeiro."),
        Passage("episodes", "Falámos em melhorar o desempenho do Ollama."),
    ]
    result = pack_context("Como otimizar o Ollama no Expecto?", passages, 245)
    assert len(result.text) <= 245
    assert "Ollama" in result.text
    assert result.selected >= 1
    assert result.selected + result.discarded == len(passages)
    assert "cor preferida" not in result.text


def test_duplicate_passages_are_not_reinserted():
    passages = [
        Passage("notes", "Memória local sobre o Ollama."),
        Passage("episodes", "  MEMÓRIA LOCAL SOBRE O OLLAMA.  "),
        Passage("documents", "Outra fonte relevante sobre o Ollama."),
    ]
    got = pack_context("Ollama", passages, 1000)
    assert got.selected == 2
    assert got.discarded == 1
    assert "Outra fonte" in got.text


def test_budget_never_cuts_a_source_url():
    long = "Manual sobre contextos: " + ("palavra " * 200) + "[URL: https://example.org/evidence]"
    passages = [
        Passage("documents", long),
        Passage("notes", "Memória sobre contexto útil."),
    ]
    packed = pack_context("contexto", passages, 120)
    assert len(packed.text) <= 120
    assert "https://example.org/evidence" not in packed.text
    assert "Memória" in packed.text


def test_sections_balanced_and_privacy_no_storage():
    passages = [
        Passage("notes", "Ollama notes A"),
        Passage("notes", "Ollama notes B"),
        Passage("notes", "Ollama notes C"),
        Passage("temporal", "Ollama state is current"),
        Passage("documents", "Ollama docs define response format"),
    ]
    packed = pack_context("Ollama", passages, 500)
    assert "ESTADO ATUAL REGISTADO" in packed.text
    assert "FONTES RECOLHIDAS" in packed.text
    assert packed.per_section.get("notes") == 3
    assert len(packed.text) <= 500
    monitor = PerformanceMonitor()
    monitor.record(profile="standard", prep_ms=11, total_ms=30, ttft_ms=17,
                   context_chars=140, context_selected=3, context_discarded=2, ok=True)
    metrics = monitor.summary()
    assert metrics["mean_context_selected"] == 3
    assert metrics["mean_context_discarded"] == 2
    assert metrics["stores_user_content"] is False
    assert "Ollama state" not in str(metrics)


def test_off_mode_preserves_legacy_without_budget():
    passages = [Passage("summary", "Important " * 30), Passage("notes", "Details " * 30)]
    full = unranked_context(passages)
    assert "Important " * 30 in full
    assert "Details " * 30 in full
    assert pack_context("anything", passages, 0).text == ""


def test_tiny_budgets_terminate_without_overflow():
    passages = [Passage("notes", "Texto com origem https://example.com")]
    for limit in range(0, 100):
        packed = pack_context("Texto", passages, limit)
        assert len(packed.text) <= limit
