"""Compare two saved laboratory reports without invoking a model."""
import argparse
import json
from pathlib import Path
from aura.laboratory_compare import compare_reports
from aura.performance_laboratory import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    parser.add_argument('--output', default='comparison.json')
    args = parser.parse_args()
    try:
        report = compare_reports(json.loads(Path(args.baseline).read_text()),
                                 json.loads(Path(args.candidate).read_text()))
        write_report(args.output, report)
        print(json.dumps(report, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f'Comparison refused: {exc}\n')


if __name__ == '__main__':
    main()
