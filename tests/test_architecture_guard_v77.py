"""Synthetic mutation tests: detect violations, cycles and architecture creep."""
from __future__ import annotations
import json
from pathlib import Path
from aura.core.architecture import (
    _resolve_imports, find_cycles, inspect_architecture, mermaid,
)
from scripts.check_architecture import main


def write(root: Path, name: str, source: str):
    path = root / (name.replace(".", "/") + ".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_current_architecture_contract_is_enforced():
    root = Path(__file__).resolve().parents[1]
    report = inspect_architecture(root)
    assert len(report.modules) >= 70
    assert report.ok, "\n".join(report.violations)
    assert report.governed_cycles == ()
    assert "aura.llm_pipeline.context" in {m.name for m in report.modules}
    assert not report.violations
    assert main(["--root", str(root), "--check"]) == 0


def test_import_resolver_handles_relative_and_absolute_modules(tmp_path):
    write(tmp_path, "aura.core.__init__", "")
    write(tmp_path, "aura.core.ports", "from typing import Protocol\n")
    write(tmp_path, "aura.core.services",
          "from .ports import Something\nimport aura.llm_pipeline.context\n")
    write(tmp_path, "aura.llm_pipeline.__init__", "")
    write(tmp_path, "aura.llm_pipeline.context", "from ..core import ports\n")
    report = inspect_architecture(tmp_path)
    assert ("aura.core.services", "aura.core.ports") in report.edges
    assert ("aura.core.services", "aura.llm_pipeline.context") in report.edges
    assert ("aura.llm_pipeline.context", "aura.core.ports") in report.edges
    assert report.ok


def test_rejects_infrastructure_import_from_ports(tmp_path):
    write(tmp_path, "aura.core.__init__", "")
    write(tmp_path, "aura.core.ports", "from aura.database import Database\n")
    write(tmp_path, "aura.database", "class Database: pass\n")
    report = inspect_architecture(tmp_path)
    assert not report.ok
    assert any("import proibido" in item for item in report.violations)
    assert main(["--root", str(tmp_path), "--check", "--format", "json"]) == 1


def test_rejects_llm_pipeline_reverse_dependency(tmp_path):
    write(tmp_path, "aura.llm_pipeline.__init__", "")
    write(tmp_path, "aura.llm_pipeline.inference",
          "from aura.memory import MemoryEngine\n")
    write(tmp_path, "aura.memory", "class MemoryEngine: pass\n")
    report = inspect_architecture(tmp_path)
    assert not report.ok
    assert any("aura.memory" in item for item in report.violations)


def test_detects_synthetic_cycles_and_reports_without_user_data(tmp_path):
    graph = {
        "x": frozenset({"y"}),
        "y": frozenset({"x"}),
        "z": frozenset(),
    }
    assert find_cycles(graph) == (("x", "y"),)
    write(tmp_path, "aura.core.__init__", "")
    write(tmp_path, "aura.core.first", "from .second import Something\n")
    write(tmp_path, "aura.core.second", "from .first import Something\n")
    report = inspect_architecture(tmp_path)
    assert report.governed_cycles == (("aura.core.first", "aura.core.second"),)
    assert not report.ok
    assert "private secret user" not in json.dumps(report.summary())


def test_governed_module_budget_and_generated_diagram(tmp_path):
    write(tmp_path, "aura.llm_pipeline.__init__", "")
    write(tmp_path, "aura.llm_pipeline.prompt", "\n".join(["x=1"] * 270))
    report = inspect_architecture(tmp_path)
    assert any("limite 260" in issue for issue in report.violations)
    diagram = mermaid(report)
    assert diagram.startswith("flowchart LR\n")
    assert '["Pipeline IA"]' in diagram
    assert "x=1" not in diagram


def test_service_inventory_is_side_effect_free(tmp_path):
    from aura.config import Settings
    from aura.database import Database
    from aura.core.services import CoreServices
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "service_manifest.sqlite3", require_encryption=False)
    services = CoreServices(settings, db)
    before = services.initialized
    manifest = services.public_manifest()
    assert manifest["initialized"] == []
    assert manifest["scope"] == "engine"
    assert "llm" in manifest["available"]
    assert services.initialized == before
    assert "passphrase" not in json.dumps(manifest)

def test_integrated_domains_have_guarded_import_boundaries(tmp_path):
    write(tmp_path, "aura.memory_commands.__init__", "")
    write(tmp_path, "aura.memory_commands.episodes",
          "from aura.engine import AuraEngine\n")
    write(tmp_path, "aura.engine", "class AuraEngine: pass\n")
    report = inspect_architecture(tmp_path)
    assert any("aura/ memory" not in issue and
               "memory_commands/episodes.py: import proibido" in issue
               for issue in report.violations)

    write(tmp_path, "aura.book_reasoning_components.__init__", "")
    write(tmp_path, "aura.book_reasoning_components.study",
          "from aura.book_reasoning import BookReasoningEngine\n")
    write(tmp_path, "aura.book_reasoning", "class BookReasoningEngine: pass\n")
    report = inspect_architecture(tmp_path)
    assert any("book_reasoning_components/study.py: import proibido" in issue
               for issue in report.violations)


def test_cycle_between_book_components_is_rejected(tmp_path):
    write(tmp_path, "aura.book_reasoning_components.__init__", "")
    write(tmp_path, "aura.book_reasoning_components.study",
          "from .questions import x\n")
    write(tmp_path, "aura.book_reasoning_components.questions",
          "from .study import x\n")
    report = inspect_architecture(tmp_path)
    assert not report.ok
    assert report.governed_cycles == ((
        "aura.book_reasoning_components.questions",
        "aura.book_reasoning_components.study",
    ),)

