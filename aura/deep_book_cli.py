"""Run: python -m aura.deep_book_cli --db PATH chapters|study|links ..."""
import argparse,json
from pathlib import Path
from .config import Settings
from .database import Database
from .deep_books import DeepBookStudy

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',default=None)
    sub=p.add_subparsers(dest='action',required=True)
    ch=sub.add_parser('chapters');ch.add_argument('book_id');ch.add_argument('--pdf',default=None)
    study=sub.add_parser('study');study.add_argument('chapter_id')
    links=sub.add_parser('links');links.add_argument('--book',default=None)
    args=p.parse_args(); settings=Settings.from_env()
    db=Database(Path(args.db) if args.db else settings.data_dir/'aura.sqlite3',
                passphrase=settings.database_passphrase,
                require_encryption=settings.database_encryption_required if not args.db else False)
    engine=DeepBookStudy(db)
    result=(engine.chapterize(args.book_id,args.pdf) if args.action=='chapters' else
            engine.study(args.chapter_id) if args.action=='study' else engine.links(args.book))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
