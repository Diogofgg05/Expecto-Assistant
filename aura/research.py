"""Bounded, source-attributed retrieval. Remote page text is data, never instructions."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import quote
import httpx
from .database import Database

HEADERS = {'User-Agent': 'AURA-Ultimate-Research-MVP/2.0 (local assistant; no bulk crawling)',
           'Accept': 'application/json'}

@dataclass
class ResearchOutcome:
    topic: str
    documents: list[dict]
    warning: str = ''


class Researcher:
    def __init__(self, db: Database, searxng_url: str = ''):
        self.db = db
        self.searxng_url = searxng_url

    async def learn(self, topic: str) -> ResearchOutcome:
        topic = topic.strip()[:160]
        if len(topic) < 2:
            return ResearchOutcome(topic, [], 'Indica um tema com pelo menos dois caracteres.')
        documents = []
        warnings = []
        async with httpx.AsyncClient(timeout=13.0, follow_redirects=True, headers=HEADERS) as client:
            # Wikipedia's public API is used as a factual starting point, not as definitive proof.
            try:
                response = await client.get('https://pt.wikipedia.org/w/api.php', params={
                    'action': 'query', 'generator': 'search', 'gsrsearch': topic,
                    'gsrlimit': '3', 'prop': 'extracts|info', 'exintro': '1',
                    'explaintext': '1', 'inprop': 'url', 'format': 'json',
                    'formatversion': '2',
                })
                response.raise_for_status()
                pages = response.json().get('query', {}).get('pages', [])
                for page in pages:
                    excerpt = (page.get('extract') or '').strip()
                    title = (page.get('title') or topic)[:240]
                    url = page.get('fullurl') or f'https://pt.wikipedia.org/wiki/{quote(title.replace(" ", "_"))}'
                    if len(excerpt) < 60 or not url.startswith('https://pt.wikipedia.org/'):
                        continue
                    item = self.db.remember_document(topic, title, excerpt, url, 'wikipedia', 'single_source')
                    documents.append(item)
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                warnings.append(f'Wikipedia indisponível: {type(exc).__name__}.')

            # Optional search snippets are provisional; never present them as verified findings.
            if self.searxng_url:
                try:
                    response = await client.get(f'{self.searxng_url}/search', params={
                        'q': topic, 'format': 'json', 'language': 'pt-PT', 'safesearch': '1'})
                    response.raise_for_status()
                    for result in response.json().get('results', [])[:5]:
                        url = str(result.get('url', ''))
                        if not url.startswith('https://'):
                            continue
                        snippet = (result.get('content') or '').strip()
                        title = (result.get('title') or topic).strip()
                        if len(snippet) < 35:
                            continue
                        item = self.db.remember_document(topic, title, snippet, url, 'search_snippet', 'unverified_preview')
                        documents.append(item)
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    warnings.append(f'SearXNG indisponível: {type(exc).__name__}.')

        if not documents and not warnings:
            warnings.append('Não foram encontrados resultados suficientes para guardar.')
        return ResearchOutcome(topic, documents, ' '.join(warnings))
