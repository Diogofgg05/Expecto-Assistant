"""Read-only panel projection and scheduled workers for AuraEngine.

Keeping these services separate makes the main command router easier to
audit; task intent still originates in the engine and is never inferred
from untrusted LLM output.
"""
from __future__ import annotations
import asyncio
import re
from functools import cached_property
from .relations import DISPLAY as RELATION_DISPLAY


class EngineServicesMixin:
    @cached_property
    def research(self):
        return self.services.get("research")

    @cached_property
    def extractor(self):
        return self.services.get("extractor")

    @cached_property
    def relations(self):
        return self.services.get("relations")

    @cached_property
    def consolidation(self):
        return self.services.get("consolidation")

    @cached_property
    def learning(self):
        return self.services.get("learning")

    @cached_property
    def optimizer(self):
        return self.services.get("optimizer")

    @cached_property
    def epistemics(self):
        return self.services.get("epistemics")

    @cached_property
    def quality(self):
        return self.services.get("quality")

    @cached_property
    def factcheck(self):
        return self.services.get("factcheck")

    @cached_property
    def continuity(self):
        return self.services.get("continuity")

    @cached_property
    def reflection(self):
        return self.services.get("reflection")

    @cached_property
    def secure_backups(self):
        return self.services.get("secure_backups")

    @staticmethod
    def _summary_rows(summaries: list[dict]) -> list[dict]:
        return [{**x, 'category':'summary', 'updated_at':x['created_at']} for x in summaries]

    @staticmethod
    def _relational_row(edge: dict) -> dict:
        label=(f"{RELATION_DISPLAY.get(edge['source_kind'],edge['source_kind'])} "
               f"{edge['source_name']} {RELATION_DISPLAY.get(edge['relation_type'],edge['relation_type'])} "
               f"{RELATION_DISPLAY.get(edge['target_kind'],edge['target_kind'])} {edge['target_name']}")
        return {**edge,'category':'relation','content':label,
                'created_at':edge['created_at'],'updated_at':edge['created_at']}

    @staticmethod
    def _topic_from(original: str) -> str:
        # Capture after the final literal 'sobre', if any; otherwise after first verb.
        m = re.search(r'\bsobre\s+(.+)$', original, flags=re.I)
        topic = m.group(1) if m else re.sub(r'^\S+\s+', '', original)
        return topic.strip().rstrip('.!?')[:160]

    async def panel_data(self, panel: str):
        if panel == 'memory':
            return self.db.combined_memory_panel(self.settings.episodic_lookback_months)
        if panel == 'research' or panel == 'browser':
            return {'topic': '', 'documents': self.db.documents(limit=25),
                    'claims':self.learning.claims(limit=18), 'warning': ''}
        if panel == 'jobs':
            return self.db.jobs()
        if panel == 'diagnostics':
            return {'ollama': await self.llm.health(), 'performance': self.llm.metrics.summary(),
                    'performance_mode': self.settings.performance_mode,
                    'memory_count': len(self.db.memories(100)),
                    'knowledge_count': len(self.db.documents(limit=200)),
                    'episodes_6months': self.db.episode_count(self.settings.episodic_lookback_months),
                    'episodic_capture': self.db.capture_enabled(self.settings.episodic_capture),
                    'memory_months': self.settings.episodic_lookback_months,
                    'semantic_indexed':self.db.episode_vector_count(self.settings.embedding_model,self.settings.episodic_lookback_months) if self.settings.embedding_model else 0,
                    'extracted_knowledge':self.db.extracted_count(),
                    'temporal_facts':self.db.temporal_count(),
                    'relation_links':self.relations.stats()['links'],
                    'consolidation': self.consolidation.stats(),
                    'advanced_learning':self.learning.stats(),
                    'optimization_lab':self.optimizer.status(),
                    'epistemic_audits':self.epistemics.latest(10),
                    'learning_quality':self.quality.overview(12),
                    'extraction_active':self.db.get_option('auto_extract_memory','true' if self.settings.auto_extract_memory else 'false')=='true',
                    'private_mode': self.db.get_option('private_mode','false')=='true',
                    'encrypted_backups_enabled': self.secure_backups.enabled,
                    'active_database_encrypted': self.db.encrypted,
                    'research_jobs': len(self.db.jobs(True)), 'research_provider':
                    'Wikipedia + SearXNG' if self.settings.searxng_url else 'Wikipedia'}
        if panel == 'projects':
            return {'message': 'Painel de projetos demonstrativo. A leitura de repositórios locais ainda não está implementada.',
                    'projects': ['Expecto Ultimate']}
        return None

    async def memory_daemon(self, stop: asyncio.Event):
        """Bounded indexing/extraction. Never starts if recording was switched off."""
        while not stop.is_set():
            policy = self.llm.nanomemory.decide('standard')
            # Pause optional background extraction when available RAM is
            # critically low; pending records remain in the database.
            if policy.low_memory:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.settings.memory_worker_interval_seconds)
                except asyncio.TimeoutError:
                    pass
                continue
            if (self.db.capture_enabled(self.settings.episodic_capture) and
                self.db.get_option('private_mode','false') != 'true'):
                if self.settings.embedding_model:
                    batch = 2 if policy.effective == 'eco' else 12
                    await self.memory.index_episode_pending(self.settings.episodic_lookback_months, batch)
                enabled = self.db.get_option('auto_extract_memory',
                    'true' if self.settings.auto_extract_memory else 'false')=='true'
                if enabled:
                    await self.extractor.extract_one()
                auto = self.db.get_option('auto_consolidate_memory',
                    'true' if self.settings.auto_consolidate_memory else 'false')=='true'
                if auto and enabled:
                    await asyncio.to_thread(self.consolidation.if_due,
                        self.settings.episodic_lookback_months)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.memory_worker_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def research_daemon(self, stop: asyncio.Event):
        """No silent system modification: only opt-in public-topic research."""
        while not stop.is_set():
            # Deferral, never deletion: opt-in jobs remain due until RAM clears.
            if self.llm.nanomemory.decide('standard').low_memory:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass
                continue
            for job in self.db.due_jobs():
                if stop.is_set():
                    break
                try:
                    result = await self.research.learn(job['topic'])
                    if (self.db.get_option('advanced_learning_enabled','false')=='true'
                        and self.db.get_option('private_mode','false')!='true'):
                        advanced = await self.learning.learn_from(job['topic'],result.documents,result.warning)
                        self.db.job_result(job['topic'],advanced.warning)
                    else:
                        self.db.job_result(job['topic'], result.warning)
                except Exception as exc:
                    # Do not write sensitive exception internals to persistent storage.
                    self.db.job_result(job['topic'], type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass
