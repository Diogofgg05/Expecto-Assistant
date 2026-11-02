"""AURA memory v2.1: durable structured notes, FTS and opt-in Ollama embeddings.

No new server or external SaaS. Ollama embeddings are optional and never required
for writing/deleting notes. Raw user text never goes to public web search.
"""
from __future__ import annotations
import json
import math
import heapq
import asyncio
import httpx
from contextlib import asynccontextmanager
from contextvars import ContextVar
from .config import Settings
from .database import Database


def cosine(left: list[float], right: list[float], *, left_norm: float | None = None) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    total = sum(a * b for a, b in zip(left, right))
    squared_norm = sum(a*a for a in left) if left_norm is None else left_norm
    denom = math.sqrt(squared_norm * sum(b*b for b in right))
    return total / denom if denom else 0.0



def top_semantic(query: list[float], candidates, *, threshold: float,
                 limit: int, always_ids: set[str] | None = None):
    """Exact cosine top-k over a streaming vector iterator, O(k) extra RAM.

    Every candidate is still checked (no approximate search or loss of recall).
    Ties are stable in input order. The retained candidates contain only ids,
    scores and scan positions; text is fetched separately for winners.
    """
    heap = []
    forced = {}
    protected = always_ids or set()
    norm = sum(x * x for x in query)
    for position, (ident, encoded) in enumerate(candidates):
        try:
            similarity = cosine(query, json.loads(encoded), left_norm=norm)
        except (ValueError, TypeError, OverflowError):
            continue
        if similarity < threshold or not math.isfinite(similarity):
            continue
        if ident in protected:
            forced[ident] = similarity
        item = (similarity, -position, ident)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    ranked = sorted(heap, reverse=True)
    return [(ident, score, -negative_position) for score, negative_position, ident in ranked], forced

class MemoryEngine:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self.model = settings.embedding_model.strip()
        # Query-scoped cache only: no sensitive queries retained after a turn.
        self._query_cache = ContextVar('expecto_query_embedding_cache', default=None)
        self._client = None

    def _transport(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=2.0),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                trust_env=False)
        return self._client

    async def aclose(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    @asynccontextmanager
    async def query_scope(self):
        """Single-flight embedding for concurrent note and episode retrieval.

        The context is copied into asyncio.gather tasks. Equal queries share
        ONE outbound embedding request, with no cross-user persistent cache.
        """
        cache = {}
        token = self._query_cache.set(cache)
        try:
            yield
        finally:
            self._query_cache.reset(token)
            for pending in cache.values():
                if not pending.done():
                    pending.cancel()

    async def _embed(self, text: str) -> list[float] | None:
        if not self.model:
            return None
        text = text[:2000]
        cache = self._query_cache.get()
        if cache is None:
            return await self._embed_uncached(text)
        key = (self.model, text)
        if key not in cache:
            cache[key] = asyncio.create_task(self._embed_uncached(text))
        return await asyncio.shield(cache[key])

    async def _embed_uncached(self, text: str) -> list[float] | None:
        try:
            response = await self._transport().post(
                self.settings.ollama_url + '/api/embed',
                json={'model': self.model, 'input': text},
                timeout=httpx.Timeout(8, connect=2),
            )
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

    async def recall(self, question: str, limit: int = 7) -> list[dict]:
        limit = max(1, min(limit, 20))
        lexical = self.db.search_memories(question, limit=max(8, limit * 3))
        scores: dict[str, float] = {}
        notes: dict[str, dict] = {}
        for n, entry in enumerate(lexical):
            notes[entry['id']] = entry
            scores[entry['id']] = 1.5 / (1 + n) + 0.06 * int(entry.get('importance', 3))
        if self.model and self.db.has_memory_vectors(self.model):
            query_vector = await self._embed(question)
            if query_vector:
                selected, matched_lexical = top_semantic(
                    query_vector, self.db.iter_memory_vectors(self.model, 2500),
                    threshold=0.39, limit=limit, always_ids=set(notes))
                for ident, similarity in matched_lexical.items():
                    scores[ident] += similarity * 2
                # Reconstitute previous stable ordering on ties.
                newcomers = sorted(
                    ((ident, sim, pos) for ident, sim, pos in selected
                     if ident not in notes),
                    key=lambda entry: entry[2])
                hydrated = self.db.memory_rows_by_ids([ident for ident, _, _ in newcomers])
                loaded = {entry['id']: entry for entry in hydrated}
                for ident, similarity, _ in newcomers:
                    if ident in loaded:
                        notes[ident] = loaded[ident]
                        scores[ident] = similarity * 2
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
            r=await self._transport().post(self.settings.ollama_url+'/api/embed',json={
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

    async def recall_episodes(self, question: str, months: int = 6, limit: int = 8) -> list[dict]:
        """Hybrid retrieval of 6-month conversations: BM25 plus local cosine.

        Never sends text off-device. Old transcript records without embeddings
        remain searchable lexically while the background batch index catches up.
        """
        limit=max(1,min(int(limit),30))
        lexical=self.db.search_episodes(question, months, limit=30)
        collected={item['id']:dict(item) for item in lexical}
        scores={item['id']:1.0/(30+rank) for rank,item in enumerate(lexical)}
        if self.model and self.db.has_episode_vectors(self.model, months):
            query_vec = await self._embed(question[:2000])
            if query_vec:
                selected, _ = top_semantic(
                    query_vec, self.db.iter_episode_vectors(self.model, months),
                    threshold=0.56, limit=50)
                hydrated = self.db.episode_rows_by_ids(
                    [ident for ident, _, _ in selected], months)
                loaded = {entry['id']: entry for entry in hydrated}
                for rank, (ident, similarity, _) in enumerate(selected):
                    if ident in loaded:
                        collected[ident] = loaded[ident]
                        scores[ident] = scores.get(ident, 0) + 1.0 / (30 + rank)
                        collected[ident]['semantic_score'] = round(similarity, 3)
        return [collected[key] for key in sorted(scores,key=lambda k:scores[k],reverse=True)[:limit]]
