"""Document ingestion and page provenance without requiring heavy Docling runtime."""
from types import SimpleNamespace as NS
import pytest
from aura.book_docling import extract_docling_pages
from aura.books import BookLearningEngine
from aura.database import Database

class FakeDocument:
    def iterate_items(self):
        yield NS(label='text',text='A equação descreve o movimento da partícula.',prov=[NS(page_no=1)]),1
        yield NS(label='table',prov=[NS(page_no=2)],export_to_markdown=lambda doc: '| x | y |\n|---|---|\n|1|2|'),1
        yield NS(label='formula',text='E = m c²',prov=[NS(page_no=2)]),1
        yield NS(label='text',text='Sem paginação!',prov=[]),1

class FakeConverter:
    def convert(self,path):return NS(document=FakeDocument())

def test_structured_extract_keeps_true_page_numbers():
    pages,d=extract_docling_pages('fake.pdf',2,converter=FakeConverter())
    assert 'equação' in pages[1]
    assert '|1|2|' in pages[2]
    assert 'E = m c²' in pages[2]
    assert d['tables']==1 and d['formulas']==1 and d['unindexed_items']==1

def test_docling_requires_provenance():
    class C:
        def convert(self,path):
            return NS(document=NS(iterate_items=lambda: iter([(NS(label='text',text='x',prov=[]),None)])))
    with pytest.raises(ValueError,match='rastreáveis'):
        extract_docling_pages('fake.pdf',2,converter=C())

def test_auto_without_docling_works_and_does_not_invent_pages(tmp_path,monkeypatch):
    fitz=pytest.importorskip('fitz')
    pdf=tmp_path/'two.pdf'
    with fitz.open() as f:
        f.new_page().insert_text((60,60),'Quimica envolve atomos e ligacoes.');f.save(pdf)
    db=Database(tmp_path/'db.sqlite3',require_encryption=False)
    from aura import book_docling
    def unavailable(*a,**kw):raise RuntimeError('not installed')
    monkeypatch.setattr(book_docling,'extract_docling_pages',unavailable)
    r=BookLearningEngine(db).import_pdf(pdf,rights_confirmed=True,rights_note='Ficção criada para testes',parser='auto')
    assert r['extraction']['parser']=='pymupdf'
    assert 'fallback_reason' in r['extraction']
    assert BookLearningEngine(db).search('atomos')[0]['page']==1

def test_invalid_parser_and_permission(tmp_path):
    pdf=tmp_path/'x.pdf';pdf.write_bytes(b'%PDF-1.4')
    db=Database(tmp_path/'db.sqlite3',require_encryption=False)
    with pytest.raises(PermissionError):BookLearningEngine(db).import_pdf(pdf,parser='docling')
    with pytest.raises(ValueError,match='Parser inválido'):
        # valid generated PDF to reach parser validation
        import fitz
        with fitz.open() as doc:doc.new_page().insert_text((50,50),'Texto');doc.save(pdf)
        BookLearningEngine(db).import_pdf(pdf,rights_confirmed=True,rights_note='Teste',parser='unknown')
