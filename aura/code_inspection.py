"""Bounded Python source inspection. Never imports or executes submitted code.

Static heuristics only: aliases are resolved from explicit imports, not full dataflow.
"""
import ast

MAX_SOURCE = 150_000
MAX_NODES = 16_000
MAX_FINDINGS = 60

REMEDIATIONS = {
    "dynamic-execution": "Evita eval/exec com dados externos; usa parsing e operações permitidas.",
    "pickle-deserialization": "Não uses pickle com dados não confiáveis; prefere JSON validado.",
    "shell-subprocess": "Usa argumentos em lista e shell=False, validando entradas.",
    "os-system": "Prefere subprocess.run com argumentos em lista e shell=False.",
    "bare-except": "Captura exceções específicas e preserva interrupções.",
    "large-function": "Divide responsabilidades em funções menores, quando adequado.",
}


def _known_imports(tree):
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".")[0]
                aliases[item.asname or root] = item.name if item.asname else root
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = node.module + "." + item.name
    return aliases


def _call_name(func, aliases):
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        root = aliases.get(func.value.id, func.value.id)
        return root + "." + func.attr
    return None


def inspect_python(source: str) -> dict:
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise ValueError("Invalid Python source length")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"valid_syntax": False, "syntax_error": {"line": exc.lineno,
                "offset": exc.offset, "message": exc.msg}, "findings": [],
                "verification": "syntax_only_no_execution"}
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ValueError("Source too complex for bounded inspection")
    aliases = _known_imports(tree)
    findings = []

    def report(node, rule, severity, description):
        if len(findings) < MAX_FINDINGS:
            findings.append({
                "line": getattr(node, "lineno", None),
                "column": getattr(node, "col_offset", None),
                "rule": rule, "severity": severity,
                "message": description,
                "suggestion": REMEDIATIONS[rule],
            })

    for node in nodes:
        if isinstance(node, ast.Call):
            name = _call_name(node.func, aliases)
            if name in ("eval", "exec", "builtins.eval", "builtins.exec"):
                report(node, "dynamic-execution", "high", "Dynamic execution needs a security review")
            elif name in ("pickle.load", "pickle.loads"):
                report(node, "pickle-deserialization", "high", "Untrusted pickle data can execute code")
            elif name in ("os.system", "os.popen"):
                report(node, "os-system", "high", "Shell command execution needs a security review")
            elif name in ("subprocess.run", "subprocess.Popen", "subprocess.call",
                          "subprocess.check_output", "subprocess.check_call"):
                if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                       and keyword.value.value is True for keyword in node.keywords):
                    report(node, "shell-subprocess", "high", "shell=True requires explicit review")
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            report(node, "bare-except", "medium", "Bare except may hide interrupts and failures")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) > 45:
            report(node, "large-function", "low", "Consider splitting large function")
    findings.sort(key=lambda f: (f["line"] if f["line"] is not None else 0, f["rule"]))
    return {"valid_syntax": True, "syntax_error": None, "findings": findings,
            "nodes_inspected": len(nodes), "verification": "static_heuristics_no_execution"}
