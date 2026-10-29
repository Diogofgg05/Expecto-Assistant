"""AURA memory v2.1: durable structured notes, FTS and opt-in Ollama embeddings.

No new server or external SaaS. Ollama embeddings are optional and never required
for writing/deleting notes. Raw user text never goes to public web search.
"""
from __future__ import annotations
import json
import math
import asyncio
import heapq
import httpx
from .config import Settings
from .database import Database

_UNSET = object()  # distinguishes absent vector from a failed/empty embedding


def cosine(left: list[float], right: list[float], *,
           left_norm: float | None = None) -> float:
    """Cosine similarity; a precomputed query norm avoids repeated work."""
    if len(left) != len(right) or not left:
        return 0.0
    # math.sumprod (Python 3.12+) runs the hot vector arithmetic in C,
    # avoiding thousands of Python generator-loop iterations per query.
    total = math.sumprod(left, right)
    lnorm = left_norm if left_norm is not None else math.sqrt(math.sumprod(left, left))
    denom = lnorm * math.sqrt(math.sumprod(right, right))
    return total / denom if denom else 0.0


class MemoryEngine:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self.model = settings.embedding_model.strip()

    async def _embed(self, text: str) -> list[float] | None:
        if not self.model:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=2)) as client:
                response = await client.post(self.settings.ollama_url + '/api/embed',
                        json={'model': self.model, 'input': text[:2000]})
                response.raise_for_status()
                vectors = response.json().get('embeddings', [])
                if vectors and isinstance(vectors[0], list):
                    v = vectors[0]
                    if 1 <= len(v) <= 8192 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in v):
                        return [float(x) for x in v]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass  # Lexical recall remains fully functional.
        return None

    async def remember(self, content: str, category: str = 'note', importance: int = 3) -> dict:
        note = self.db.add_memory(content, category=category, importance=importance)
        if self.model:
            vector = await self._embed(note['content'])
            if vector is not None:
                self.db.set_vector(note['id'], self.model, vector)
        return note

    async def correct(self, id: str, content: str) -> dict | None:
        changed = self.db.update_memory(id, content)
        if changed is not None and self.model:
            vector = await self._embed(changed['content'])
            if vector is not None:
                self.db.set_vector(id, self.model, vector)
        return changed

    async def index_pending(self, limit: int = 30) -> dict:
        if not self.model:
            return {'indexed': 0, 'pending': 0, 'reason': 'Modelo de embeddings não configurado.'}
        pending = self.db.pending_embeddings(self.model, min(limit, 40))
        indexed = 0
        for note in pending:
            vector = await self._embed(note['content'])
            if vector is None:
                break  # Avoid repeated network failures.
            self.db.set_vector(note['id'], self.model, vector)
            indexed += 1
        return {'indexed': indexed,
                'pending': len(self.db.pending_embeddings(self.model, 10000)),
                'reason': '' if indexed or not pending else 'Ollama ou modelo de embedding indisponível.'}

    async def recall_pair(self, question: str, months: int = 6,
                          notes_limit: int = 8, episodes_limit: int = 5):
        """Share one transient query embedding across two retrieval paths.

        No embedding or query is cached persistently. Existing direct recall
        methods retain their behaviour. A failed embed falls back to lexical
        retrieval for both collections, avoiding duplicate network failures.
        """
        if not self.model:
            return await asyncio.gather(
                self.recall(question, notes_limit, query_vector=None),
                self.recall_episodes(question, months, episodes_limit,
                                     query_vector=None),
            )

        # Overlap the local FTS/SQLite lookups with the Ollama embedding request.
        # Each DB function uses its own connection; no DB cursor crosses threads.
        def lexical_pair():
            note_limit = max(1, min(notes_limit, 20))
            return (
                self.db.search_memories(question, limit=max(8, note_limit * 3)),
                self.db.search_episodes(question, months, limit=30),
            )

        vector, lexical = await asyncio.gather(
            self._embed(question[:2000]),
            asyncio.to_thread(lexical_pair),
        )
        return await asyncio.gather(
            self.recall(question, notes_limit, query_vector=vector,
                        _prefetched_lexical=lexical[0]),
            self.recall_episodes(question, months, episodes_limit,
                                 query_vector=vector,
                                 _prefetched_lexical=lexical[1]),
        )

    async def recall(self, question: str, limit: int = 7, *,
                     query_vector=_UNSET, _prefetched_lexical=_UNSET) -> list[dict]:
        limit = max(1, min(limit, 20))
        lexical = (self.db.search_memories(question, limit=max(8, limit * 3))
                   if _prefetched_lexical is _UNSET else _prefetched_lexical)
        scores: dict[str, float] = {}
        notes: dict[str, dict] = {}
        for n, entry in enumerate(lexical):
            notes[entry['id']] = entry
            scores[entry['id']] = 1.5 / (1 + n) + 0.06 * int(entry.get('importance', 3))
        if self.model:
            stored = self.db.vectors(self.model, 2500)
            if stored:
                vector = await self._embed(question) if query_vector is _UNSET else query_vector
                if vector:
                    query_norm = math.sqrt(sum(v*v for v in vector))
                    for entry in stored:
                        try:
                            score = cosine(vector, json.loads(entry['vector_json']),
                                           left_norm=query_norm)
                        except (ValueError, TypeError):
                            continue
                        if score >= 0.39:
                            notes[entry['id']] = entry
                            scores[entry['id']] = scores.get(entry['id'], 0) + score * 2
        return [notes[k] for k in sorted(scores, key=scores.get, reverse=True)[:limit]]

    async def index_episode_pending(self, months: int = 6, limit: int = 12) -> dict:
        """Backfill durable episode vectors in short, bounded batches."""
        if not self.model:
            return {'indexed':0,'pending':0,'reason':'Configura AURA_EMBEDDING_MODEL.'}
        pending=self.db.pending_episode_embeddings(self.model,months,limit)
        if not pending:
            return {'indexed':0,'pending':0,'reason':''}
        # One Ollama request for a batch is substantially cheaper than N calls.
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=2.0)) as client:
                r=await client.post(self.settings.ollama_url+'/api/embed',json={
                    'model':self.model,'input':[item['content'][:2000] for item in pending]
                })
                r.raise_for_status()
                vectors=r.json().get('embeddings',[])
            if not isinstance(vectors,list) or len(vectors)!=len(pending):
                raise ValueError('Embedding batch incompleto')
            for item,vector in zip(pending,vectors):
                self.db.save_episode_vector(item['id'],self.model,vector)
            remaining = len(self.db.pending_episode_embeddings(self.model,months,10000))
            return {'indexed':len(pending),'pending':remaining,'reason':''}
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return {'indexed':0,'pending':len(pending),'reason':'Ollama ou embeddings indisponíveis.'}

    async def recall_episodes(self, question: str, months: int = 6, limit: int = 8, *,
                              query_vector=_UNSET, _prefetched_lexical=_UNSET) -> list[dict]:
        """Hybrid retrieval of 6-month conversations: BM25 plus local cosine.

        Never sends text off-device. Old transcript records without embeddings
        remain searchable lexically while the background batch index catches up.
        """
        limit=max(1,min(int(limit),30))
        lexical=(self.db.search_episodes(question, months, limit=30)
                 if _prefetched_lexical is _UNSET else _prefetched_lexical)
        collected={item['id']:dict(item) for item in lexical}
        scores={item['id']:1.0/(30+rank) for rank,item in enumerate(lexical)}
        if self.model:
            # The embed model is shared by indexing and querying; changing models
            # uses a separate index, avoiding mixed-dimensional comparisons.
            query_vec=(await self._embed(question[:2000]) if query_vector is _UNSET
                       else query_vector)
            if query_vec:
                # Top-50 bounded min heap instead of sorting every match;
                # query norm calculated once rather than for every vector.
                candidates = []
                query_norm = math.sqrt(sum(v*v for v in query_vec))
                for position, row in enumerate(self.db.episode_vectors_in_window(self.model,months)):
                    try:
                        similarity = cosine(
                            query_vec, json.loads(row['vector_json']), left_norm=query_norm)
                    except (ValueError, TypeError, OverflowError):
                        continue
                    if similarity >= 0.56:
                        ranked = (similarity, -position, row)
                        if len(candidates) < 50:
                            heapq.heappush(candidates, ranked)
                        elif ranked > candidates[0]:
                            heapq.heapreplace(candidates, ranked)
                for rank, (similarity, _, item) in enumerate(
                        sorted(candidates, reverse=True)):
                    collected[item['id']]={k:v for k,v in item.items() if k!='vector_json'}
                    scores[item['id']]=scores.get(item['id'],0)+1.0/(30+rank)
                    collected[item['id']]['semantic_score']=round(similarity,3)
        return [collected[key] for key in sorted(scores,key=lambda k:scores[k],reverse=True)[:limit]]
