"""Bounded Python source inspection. Never imports or executes submitted code."""
import ast

MAX_SOURCE = 150_000
MAX_NODES = 16_000
MAX_FINDINGS = 60


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
    findings = []
    def report(node, rule, severity, description):
        if len(findings) < MAX_FINDINGS:
            findings.append({"line": getattr(node, "lineno", None), "rule": rule,
                             "severity": severity, "message": description})
    for node in nodes:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                report(node, "dynamic-execution", "high", "Dynamic execution needs a security review")
            elif isinstance(func, ast.Attribute) and func.attr in ("loads", "load"):
                if isinstance(func.value, ast.Name) and func.value.id == "pickle":
                    report(node, "pickle-deserialization", "high", "Untrusted pickle data can execute code")
            elif isinstance(func, ast.Attribute) and func.attr in ("run", "Popen", "call", "check_output"):
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                           and keyword.value.value is True for keyword in node.keywords):
                        report(node, "shell-subprocess", "high", "shell=True requires explicit review")
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            report(node, "bare-except", "medium", "Bare except may hide interrupts and failures")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) > 45:
                report(node, "large-function", "low", "Consider splitting large function")
    findings.sort(key=lambda f: (f["line"] if f["line"] is not None else 0, f["rule"]))
    return {"valid_syntax": True, "syntax_error": None, "findings": findings,
            "nodes_inspected": len(nodes), "verification": "static_heuristics_no_execution"}
