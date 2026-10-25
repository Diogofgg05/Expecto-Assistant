import pytest
from aura.database import Database
from aura.books import BookLearningEngine
from aura.deep_books import DeepBookStudy

def test_study_links_delete(tmp_path):
    fitz=pytest.importorskip('fitz')
    db=Database(tmp_path/'study.sqlite3',require_encryption=False)
    engine=BookLearningEngine(db); deep=DeepBookStudy(db)
    ids=[]
    for n in [1,2]:
        pdf=tmp_path/f'b{n}.pdf'
        with fitz.open() as doc:
            for _ in range(2):
                p=doc.new_page();p.insert_text((50,60),'Vetores representam grandezas com direcao e magnitude. O estudo dos vetores aparece em matematica e fisica.')
            doc.set_toc([[1,'Capitulo de vetores',1]])
            doc.save(pdf)
        book=engine.import_pdf(pdf,rights_confirmed=True,rights_note='Teste local criado aqui')
        ids.append(book['book_id'])
        chapters=deep.chapterize(book['book_id'],pdf)
        assert chapters[0]['method']=='toc'
        studied=deep.study(chapters[0]['id'])
        assert studied['citations'] and studied['concepts'] and studied['status']=='extractive_unverified'
    assert any(x['concept']=='vetores' for x in deep.links())
    engine.delete_book(ids[0]);assert not deep.links()

def test_wrong_pdf_rejected(tmp_path):
    fitz=pytest.importorskip('fitz')
    db=Database(tmp_path/'db.sqlite3',require_encryption=False)
    engine=BookLearningEngine(db);deep=DeepBookStudy(db)
    files=[]
    for n in [1,2]:
        pdf=tmp_path/f'{n}.pdf'
        with fitz.open() as d:
            p=d.new_page();p.insert_text((20,80),f'Livro original diferente numero {n}. Contem texto para teste.');d.save(pdf)
        files.append(pdf)
    b=engine.import_pdf(files[0],rights_confirmed=True,rights_note='Teste')
    with pytest.raises(ValueError,match='não corresponde'):deep.chapterize(b['book_id'],files[1])
