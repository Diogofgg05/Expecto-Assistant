"""Run: python -m aura.deep_book_cli --db PATH chapters|study|links ..."""
import argparse,json,asyncio
from pathlib import Path
from .config import Settings
from .database import Database
from .deep_books import DeepBookStudy
from .book_reasoning import BookReasoningEngine,OllamaBookModel
from .book_semantics import BookSemanticIndex,OllamaBookEncoder
from .book_mastery import BookMasteryLab
from .book_iteration import BookIterationLab
from .book_research import BookResearchEngine
from .multilayer_reasoning import MultiLayerReasoner, OllamaMultiLayerAdapter, export_graph_html
from .reasoning_verifier import ReasoningVerifier
from .algebra_verifier import verify_task
from .algebra_natural import explain

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',default=None)
    sub=p.add_subparsers(dest='action',required=True)
    research=sub.add_parser('research-books',help='Pesquisa várias questões com diversidade entre livros e rastreabilidade')
    research.add_argument('questions',nargs='+');research.add_argument('--book',default=None)
    research.add_argument('--semantic',action='store_true');research.add_argument('--limit',type=int,default=10)
    dimension=sub.add_parser('reason-3d',help='Raciocínio em cinco camadas com grafo 3D opcional')
    dimension.add_argument('question');dimension.add_argument('--book',default=None)
    dimension.add_argument('--semantic',action='store_true')
    dimension.add_argument('--html',default=None,help='Guardar visualização 3D local num ficheiro HTML')
    verified=sub.add_parser('reason-verify',help='Proposta com fontes, crítica e verificação aritmética independente')
    verified.add_argument('question');verified.add_argument('--book',default=None)
    verified.add_argument('--semantic',action='store_true')
    algebra=sub.add_parser('verify-algebra',help='Verifica matrizes e sistemas lineares usando frações exatas')
    algebra.add_argument('json_file',help='JSON com o problema e resultado afirmado')
    natural=sub.add_parser('solve-natural',help='Interpreta sistemas de 2-3 equações ou determinantes/inversas em português')
    natural.add_argument('question')
    ch=sub.add_parser('chapters');ch.add_argument('book_id');ch.add_argument('--pdf',default=None)
    study=sub.add_parser('study');study.add_argument('chapter_id')
    links=sub.add_parser('links');links.add_argument('--book',default=None)
    deep=sub.add_parser('study-ai',help='Estuda capítulo completo com Ollama local (pode demorar)')
    deep.add_argument('chapter_id')
    question=sub.add_parser('ask',help='Pergunta sobre os livros com citações verificadas')
    question.add_argument('question');question.add_argument('--book',default=None);question.add_argument('--chapter',default=None)
    compare=sub.add_parser('compare-ai',help='Compara conceitos entre dois livros')
    compare.add_argument('book_a');compare.add_argument('book_b')
    mapping=sub.add_parser('learning-map',help='Mapa conceptual e desafios com fontes (revisão necessária)')
    mapping.add_argument('run_id')
    index=sub.add_parser('index-semantic',help='Indexa um livro com embeddings locais (opt-in)')
    index.add_argument('book_id')
    check=sub.add_parser('benchmark',help='Avalia recuperação usando perguntas e passagens anotadas')
    check.add_argument('dataset',help='Ficheiro JSON com casos manualmente verificados')
    check.add_argument('--semantic',action='store_true')
    question.add_argument('--semantic',action='store_true',help='Usar embeddings locais previamente indexados')
    mastery=sub.add_parser('mastery-check',help='Avalia compreensão com questões externas e fontes gold revistas por humanos')
    mastery.add_argument('dataset',help='JSON de questões com curation=human_reviewed')
    mastery.add_argument('--semantic',action='store_true')
    mastery.add_argument('--min-f1',type=float,default=0.65)
    mastery_report=sub.add_parser('mastery-report',help='Mostra avaliação persistida e lacunas por capítulo')
    mastery_report.add_argument('run_id')
    mastery_history=sub.add_parser('mastery-history',help='Histórico de testes de compreensão')
    mastery_history.add_argument('--dataset-hash',default=None)
    mastery_plan=sub.add_parser('mastery-plan',help='Plano de novo estudo baseado nos erros')
    mastery_plan.add_argument('run_id')
    mastery_compare=sub.add_parser('mastery-compare',help='Compara duas avaliações do mesmo benchmark')
    mastery_compare.add_argument('previous_run_id');mastery_compare.add_argument('current_run_id')
    cycle=sub.add_parser('learning-cycle',help='Compara estratégias de pesquisa com treino, validação e teste reservado')
    cycle.add_argument('dataset',help='JSON com train, validation e holdout preparados por humanos')
    cycle.add_argument('--limits',type=int,nargs='+',default=[4,8,12])
    cycle.add_argument('--semantic',action='store_true')
    cycle_report=sub.add_parser('cycle-report',help='Métricas e histórico de um ciclo de aprendizagem')
    cycle_report.add_argument('run_id')
    cycle_review=sub.add_parser('cycle-review',help='Plano de releitura usando apenas o conjunto de treino')
    cycle_review.add_argument('run_id')
    restudy=sub.add_parser('cycle-restudy',help='Reestuda capítulos onde falhou no treino (com autorização)')
    restudy.add_argument('run_id')
    restudy.add_argument('--max-chapters',type=int,default=2)
    sub.add_parser('cycle-history',help='Histórico local de ciclos de aprendizagem')
    report=sub.add_parser('report',help='Mostra estudo anterior com todas as evidências')
    report.add_argument('run_id')
    args=p.parse_args()
    if args.action=='solve-natural':
        print(json.dumps(explain(args.question),ensure_ascii=False,indent=2))
        return
    if args.action=='verify-algebra':
        print(json.dumps(verify_task(json.loads(Path(args.json_file).read_text(encoding='utf-8'))),ensure_ascii=False,indent=2))
        return
    settings=Settings.from_env()
    db=Database(Path(args.db) if args.db else settings.data_dir/'aura.sqlite3',
                passphrase=settings.database_passphrase,
                require_encryption=settings.database_encryption_required if not args.db else False)
    engine=DeepBookStudy(db)
    if args.action in ('study-ai','ask','compare-ai','report','index-semantic','benchmark','learning-map','mastery-check','mastery-report','mastery-history','mastery-plan','mastery-compare','learning-cycle','cycle-report','cycle-review','cycle-history','cycle-restudy','research-books','reason-3d','reason-verify'):
        reasoning=BookReasoningEngine(db)
        model=OllamaBookModel(settings.ollama_url,settings.ollama_model)
        if args.action=='reason-verify':
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            found=asyncio.run(BookResearchEngine(db).investigate([args.question],encoder=enc,book_id=args.book,limit=8))
            evidence=[{'id':f"p:{e['passage_id']}",'text':e['text']} for e in found['evidence']]
            adapter=OllamaMultiLayerAdapter(settings.ollama_url,settings.ollama_model)
            result=asyncio.run(ReasoningVerifier(adapter).run(args.question,evidence))
            result['source_pages']=[{'id':f"p:{e['passage_id']}",'title':e['title'],'page':e['page']} for e in found['evidence']]
        elif args.action=='reason-3d':
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            adapter=OllamaMultiLayerAdapter(settings.ollama_url,settings.ollama_model)
            result=asyncio.run(MultiLayerReasoner(db).reason(args.question,adapter,encoder=enc,book_id=args.book))
            if args.html:
                html_path=Path(args.html).expanduser().resolve()
                if html_path.suffix.lower()!='.html':raise SystemExit('O destino deve terminar em .html')
                html_path.write_text(export_graph_html(result['graph']),encoding='utf-8')
                result['html_path']=str(html_path)
        elif args.action=='research-books':
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            result=asyncio.run(BookResearchEngine(db).investigate(args.questions,encoder=enc,book_id=args.book,limit=args.limit))
        elif args.action=='study-ai':result=asyncio.run(reasoning.study_chapter(args.chapter_id,model))
        elif args.action=='ask':
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            result=asyncio.run(reasoning.answer(args.question,model,book_id=args.book,chapter_id=args.chapter,encoder=enc))
        elif args.action=='learning-map':
            result=asyncio.run(reasoning.build_learning_map(args.run_id,model))
        elif args.action=='index-semantic':
            if not settings.embedding_model: raise SystemExit('Define AURA_EMBEDDING_MODEL para indexar')
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url)
            result=asyncio.run(BookSemanticIndex(db).index_book(args.book_id,enc))
        elif args.action=='mastery-check':
            dataset=json.loads(Path(args.dataset).read_text(encoding='utf-8'))
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            result=asyncio.run(BookMasteryLab(db).assess(dataset,model,encoder=enc,min_f1=args.min_f1))
        elif args.action=='learning-cycle':
            dataset=json.loads(Path(args.dataset).read_text(encoding='utf-8'))
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            result=asyncio.run(BookIterationLab(db).run(dataset,model,limits=args.limits,encoder=enc))
        elif args.action=='cycle-report':result=BookIterationLab(db).report(args.run_id)
        elif args.action=='cycle-review':result=BookIterationLab(db).review(args.run_id)
        elif args.action=='cycle-history':result=BookIterationLab(db).history()
        elif args.action=='cycle-restudy':result=asyncio.run(BookIterationLab(db).restudy(args.run_id,model,max_chapters=args.max_chapters))
        elif args.action=='mastery-report':result=BookMasteryLab(db).report(args.run_id)
        elif args.action=='mastery-history':result=BookMasteryLab(db).history(args.dataset_hash)
        elif args.action=='mastery-plan':result=BookMasteryLab(db).remediation(args.run_id)
        elif args.action=='mastery-compare':result=BookMasteryLab(db).compare(args.previous_run_id,args.current_run_id)
        elif args.action=='benchmark':
            enc=OllamaBookEncoder(settings.embedding_model,settings.ollama_url) if args.semantic else None
            data=json.loads(Path(args.dataset).read_text(encoding='utf-8'))
            result=asyncio.run(BookSemanticIndex(db).evaluate_retrieval(data,encoder=enc))
        elif args.action=='compare-ai':result=asyncio.run(reasoning.compare_books(args.book_a,args.book_b,model))
        else:result=reasoning.report(args.run_id)
    else:
        result=(engine.chapterize(args.book_id,args.pdf) if args.action=='chapters' else
                engine.study(args.chapter_id) if args.action=='study' else engine.links(args.book))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
