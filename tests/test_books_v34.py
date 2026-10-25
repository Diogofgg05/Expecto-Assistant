from pathlib import Path
import pytest
from aura.database import Database
from aura.books import BookLearningEngine

@pytest.fixture
def setup(tmp_path):
    db=Database(tmp_path/'aura.sqlite3',require_encryption=False)
    return BookLearningEngine(db)

def test_import_search_citation_and_delete(setup,tmp_path):
    fitz=pytest.importorskip('fitz')
    p=tmp_path/'book.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((40,70),'A gravidade atrai objetos com massa. A aceleracao e medida em metros por segundo quadrado.')
        page=doc.new_page();page.insert_text((40,70),'Os vetores possuem magnitude e direcao. Esta e outra pagina.')
        doc.save(p)
    with pytest.raises(PermissionError):setup.import_pdf(p)
    imported=setup.import_pdf(p,rights_confirmed=True,rights_note='Documento de teste criado localmente')
    assert imported['pages']==2
    assert setup.import_pdf(p,rights_confirmed=True,rights_note='Teste')['duplicate']
    hits=setup.search('vetores direcao')
    assert hits and hits[0]['page']==2
    with pytest.raises(ValueError): setup.propose(hits[0]['passage_id'],'Uma mentira','Não aparece no ficheiro de origem.')
    claim=setup.propose(hits[0]['passage_id'],'O documento afirma que vetores têm direção','Os vetores possuem magnitude e direcao.')
    assert claim['status']=='unverified_proposal'
    assert setup.delete_book(imported['book_id'])==1
    assert setup.search('vetores')==[]

def test_scanned_pdf_rejected(setup,tmp_path):
    fitz=pytest.importorskip('fitz');p=tmp_path/'scan.pdf'
    with fitz.open() as d:
        d.new_page();d.save(p)
    with pytest.raises(ValueError,match='OCR'):setup.import_pdf(p,rights_confirmed=True,rights_note='Teste')

def test_chunks_bounded():
    s=' '.join(['palavra']*500)
    chunks=BookLearningEngine.chunks(s,220,40)
    assert len(chunks)>5 and all(len(x)<=220 for x in chunks)
