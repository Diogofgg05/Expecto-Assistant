"""CLI: python -m aura.book_cli import /path/file.pdf --rights "CC BY 4.0; usage approved"""
import argparse,json
from pathlib import Path
from .database import Database
from .books import BookLearningEngine
from .config import Settings

def main():
    p=argparse.ArgumentParser(description='AURA: biblioteca PDF local com citações por página')
    p.add_argument('--db',default=None,help='Caminho da base (predefinição: Settings da AURA)')
    sub=p.add_subparsers(dest='action',required=True)
    imp=sub.add_parser('import');imp.add_argument('file');imp.add_argument('--rights',required=True)
    q=sub.add_parser('search');q.add_argument('question')
    sub.add_parser('list')
    rm=sub.add_parser('delete');rm.add_argument('book_id')
    args=p.parse_args(); settings=Settings.from_env()
    db=Database(Path(args.db) if args.db else settings.data_dir/'aura.sqlite3',passphrase=settings.database_passphrase,
                require_encryption=settings.database_encryption_required if not args.db else False)
    engine=BookLearningEngine(db)
    if args.action=='import':result=engine.import_pdf(args.file,rights_confirmed=True,rights_note=args.rights)
    elif args.action=='search':result=engine.search(args.question)
    elif args.action=='list':result=engine.books()
    else:result={'deleted':engine.delete_book(args.book_id)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
