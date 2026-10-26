"""Optional Docling adapter. Preserve page provenance; never guess missing page labels."""
from __future__ import annotations
from collections import defaultdict


def extract_docling_pages(path, page_count: int, converter=None):
    """Return indexed page->text and diagnostics. Raises if provenance is absent.

    Accepts a converter override for regression tests; actual dependency is optional.
    """
    if converter is None:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise RuntimeError('Docling não instalado: pip install -r requirements-docling.txt') from exc
        converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document
    pages = defaultdict(list)
    tables = 0
    formulas = 0
    dropped = 0
    for item, _ in doc.iterate_items():
        label = str(getattr(item, 'label', '')).lower()
        prov = getattr(item, 'prov', None) or []
        page_numbers = sorted({int(p.page_no) for p in prov if getattr(p, 'page_no', None) is not None})
        if not page_numbers or any(p < 1 or p > page_count for p in page_numbers):
            dropped += 1
            continue
        text = ''
        if 'table' in label:
            tables += 1
            try:
                text = item.export_to_markdown(doc=doc)
            except (AttributeError, TypeError):
                text = ''
        else:
            text = str(getattr(item, 'text', '') or '').strip()
            if 'formula' in label:
                formulas += 1
        if not text.strip():
            dropped += 1
            continue
        # For multi-page elements, attach the text to the first referenced page;
        # never duplicate a passage over multiple pages as if the page had the text.
        pages[page_numbers[0]].append(text.strip())
    if not pages:
        raise ValueError('Docling não devolveu passagens com páginas rastreáveis; não é seguro indexar citações.')
    return {p:'\n'.join(items) for p,items in sorted(pages.items())}, {
        'tables':tables, 'formulas':formulas, 'unindexed_items':dropped,
        'pages_with_content':len(pages), 'parser':'docling',
    }
