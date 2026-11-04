"""Inspect and enforce EXPECTO architectural boundaries without Ollama.

Usage: python -m scripts.check_architecture --check
       python -m scripts.check_architecture --format json
       python -m scripts.check_architecture --format mermaid
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from aura.core.architecture import inspect_architecture, mermaid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EXPECTO architecture guardian")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Exit 1 on violation")
    parser.add_argument("--format", choices=("text", "json", "mermaid"), default="text")
    args = parser.parse_args(argv)

    report = inspect_architecture(args.root)
    if args.format == "json":
        print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
    elif args.format == "mermaid":
        print(mermaid(report), end="")
    else:
        summary = report.summary()
        print(f"EXPECTO Architecture: {summary['module_count']} modules, "
              f"{summary['internal_import_count']} internal imports")
        for item in summary["largest_modules"]:
            print(f"  {item['lines']:4} lines  {item['module']}")
        for item in report.violations:
            print("ERROR: " + item)
        if report.ok:
            print("PASS: architecture boundaries, layer cycles, module budgets")
    return 1 if args.check and not report.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
