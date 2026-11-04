"""EXPECTO architecture auditor: static imports, module boundaries and complexity.

Standard library only. Reads source code, never imports analyzed modules,
starts model services, opens the database or reads private user memory.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Module:
    name: str
    path: str
    lines: int
    imports: frozenset[str]


@dataclass(frozen=True)
class ArchitectureReport:
    modules: tuple[Module, ...]
    edges: tuple[tuple[str, str], ...]
    governed_cycles: tuple[tuple[str, ...], ...]
    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> dict:
        ranked = sorted(self.modules, key=lambda x: (-x.lines, x.name))
        return {
            "ok": self.ok,
            "module_count": len(self.modules),
            "internal_import_count": len(self.edges),
            "governed_cycles": [list(cycle) for cycle in self.governed_cycles],
            "violations": list(self.violations),
            "largest_modules": [
                {"module": m.name, "lines": m.lines} for m in ranked[:10]
            ],
            "scope": "static Python imports; guarded layers only",
        }


def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_imports(tree: ast.AST, module: str, is_package: bool,
                     known: frozenset[str]) -> frozenset[str]:
    package = module.split(".") if is_package else module.split(".")[:-1]
    resolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name in known:
                    resolved.add(imported.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package):
                    continue
                start = package[:len(package) - (node.level - 1)]
                suffix = node.module.split(".") if node.module else []
                target = ".".join(start + suffix)
            else:
                target = node.module or ""
            if target in known:
                resolved.add(target)
            # Also capture explicit submodule imports from a parent package.
            for alias in node.names:
                candidate = target + "." + alias.name
                if candidate in known:
                    resolved.add(candidate)
    resolved.discard(module)
    return frozenset(resolved)


def scan_modules(root: Path) -> tuple[Module, ...]:
    """Index source imports without importing the application or optional deps."""
    folder = root / "aura"
    if not folder.is_dir():
        raise ValueError("Não encontrei o pacote aura na raiz do projeto")
    paths = sorted(folder.rglob("*.py"))
    known = frozenset(_module_name(path, root) for path in paths)
    modules = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        name = _module_name(path, root)
        imports = _resolve_imports(tree, name, path.name == "__init__.py", known)
        modules.append(Module(name=name, path=path.relative_to(root).as_posix(),
                              lines=len(source.splitlines()), imports=imports))
    return tuple(modules)


def find_cycles(graph: dict[str, frozenset[str]]) -> tuple[tuple[str, ...], ...]:
    """Tarjan SCC, deterministic output; only cycles among indexed nodes."""
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[tuple[str, ...]] = []

    def visit(node: str):
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph[node]):
            if target not in graph:
                continue
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1 or node in graph[node]:
                cycles.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return tuple(sorted(cycles))


GOVERNED_DOMAINS = (
    "aura.core",
    "aura.llm_pipeline",
    "aura.memory_commands",
    "aura.book_reasoning_components",
)


def _governed(name: str) -> bool:
    """Include package initializers and their submodules in the boundary."""
    return any(name == domain or name.startswith(domain + ".")
               for domain in GOVERNED_DOMAINS)


def _forbidden(source: str, target: str) -> bool:
    """Enforce narrowly scoped, low-risk dependency direction contracts."""
    if source == "aura.core.ports":
        return target.startswith("aura.")
    if source == "aura.llm_pipeline.inference":
        return target.startswith("aura.")
    if source == "aura.llm_pipeline.prompt":
        return target.startswith("aura.") and target != "aura.identity"
    if source == "aura.llm_pipeline.context":
        return (target in {"aura.llm", "aura.engine", "aura.app",
                           "aura.core.services"} or
                target.startswith("aura.api_routes_"))
    if source == "aura.core.services":
        return (target in {"aura.app", "aura.engine"} or
                target.startswith("aura.api_routes_"))
    if source.startswith(("aura.memory_commands.", "aura.book_reasoning_components.")):
        # Domain implementation must not reach back into interactive entrypoints.
        return (target in {"aura.app", "aura.engine", "aura.llm",
                           "aura.core.services", "aura.book_reasoning"} or
                target.startswith("aura.api_routes_"))
    return False


def inspect_architecture(root: Path, *, max_layer_lines: int = 260) -> ArchitectureReport:
    if max_layer_lines < 1:
        raise ValueError("Limite de linhas inválido")
    modules = scan_modules(root)
    edges = tuple(sorted((m.name, target) for m in modules for target in m.imports))
    governed = {m.name: frozenset(t for t in m.imports if _governed(t))
                for m in modules if _governed(m.name)}
    cycles = find_cycles(governed)
    problems = []
    for m in modules:
        if _governed(m.name) and m.lines > max_layer_lines:
            problems.append(
                f"{m.path}: módulo de arquitetura com {m.lines} linhas "
                f"(limite {max_layer_lines})")
        for target in sorted(m.imports):
            if _forbidden(m.name, target):
                problems.append(f"{m.path}: import proibido de {target}")
    for cycle in cycles:
        problems.append("Dependência circular entre camadas: " + " -> ".join(cycle))
    return ArchitectureReport(modules, edges, cycles, tuple(sorted(problems)))


def mermaid(report: ArchitectureReport) -> str:
    """Derived overview of actual imports, not a manually invented diagram."""
    def group(name: str) -> str:
        if name.startswith("aura.core."):
            return "Nucleo e contratos"
        if name.startswith("aura.llm_pipeline."):
            return "Pipeline IA"
        if name.startswith("aura.memory_commands"):
            return "Comandos de memoria"
        if name.startswith("aura.book_reasoning_components"):
            return "Raciocinio em livros"
        if name == "aura.llm":
            return "Ollama"
        if name in {"aura.app", "aura.engine"} or name.startswith(
                ("aura.api_routes_", "aura.command_")):
            return "API e comandos"
        if name in {"aura.database", "aura.memory"} or name.startswith("aura.db_"):
            return "Memoria e SQL"
        if name.startswith("aura.book") or name.startswith("aura.deep_book"):
            return "Livros e RAG"
        if name in {"aura.security", "aura.vault"}:
            return "Seguranca"
        return "Servicos cognitivos"

    groups = sorted({group(m.name) for m in report.modules})
    ids = {label: f"C{i}" for i, label in enumerate(groups)}
    lines = ["flowchart LR"]
    for label in groups:
        lines.append(f'  {ids[label]}["{label}"]')
    dependencies = sorted({(group(source), group(target))
                           for source, target in report.edges
                           if group(source) != group(target)})
    for left, right in dependencies:
        lines.append(f"  {ids[left]} --> {ids[right]}")
    return "\n".join(lines) + "\n"
