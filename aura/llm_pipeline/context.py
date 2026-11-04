"""Retrieve evidence, preserve privacy boundaries and pack existing context."""
from __future__ import annotations
import asyncio
from ..context_selection import Passage, pack_context, unranked_context

async def collect_context(settings, db, memory, question, profile, memory_plan):
    if profile.retrieve_personal:
        # Independent retrievals can share the wait time.
        # Both retrievals often embed the exact same query. Share one
        # in-flight embedding within this request and drop it afterwards.
        async with memory.query_scope():
            notes, episodes = await asyncio.gather(
                memory.recall(question, 8),
                memory.recall_episodes(question, settings.episodic_lookback_months, 5),
            )
    else:
        # Only explicitly self-contained general definitions use this path.
        notes, episodes = [], []
    # Never include unbounded external data in the prompt.
    knowledge = db.documents(query=question, limit=4) if profile.retrieve_personal else []
    from ..learning import LearningEngine
    from ..quality import KnowledgeQuality
    verifier = KnowledgeQuality(db)
    learned_claims = []
    for candidate in (LearningEngine(settings,db).claims(question,5) if profile.retrieve_personal else []):
        assessment = verifier.inspect(candidate['id'])
        if assessment and assessment['decision'] != 'withhold':
            learned_claims.append(candidate)
    from ..temporal import DISPLAY
    temporal = db.temporal_current(limit=20) if profile.retrieve_personal else []
    from ..relations import RelationMemory, DISPLAY as RELATION_DISPLAY
    linked = (RelationMemory(db).search_related(question,limit=8,months=settings.episodic_lookback_months)
              if profile.retrieve_personal else [])
    from ..consolidation import ConsolidationEngine
    summary_items = ConsolidationEngine(db).summaries(question,limit=2) if profile.retrieve_personal else []
    # Rank evidence from every retrieval subsystem under ONE global budget.
    # A section is not discarded just because earlier sections were large.
    snippets: list[Passage] = []
    for x in summary_items:
        snippets.append(Passage('summary', x['content'][:1000]))
    for item in temporal:
        snippets.append(Passage(
            'temporal',
            f"- {DISPLAY.get(item['subject'], item['subject'])}: {item['value']} "
            f"(registado em {item['valid_from'][:10]})", importance=1.0,
        ))
    for item in linked:
        snippets.append(Passage(
            'relations',
            f"- {item['source_name']} "
            f"{RELATION_DISPLAY.get(item['relation_type'], item['relation_type'])} "
            f"{item['target_name']} [{item['origin']}]",
        ))
    for item in notes:
        snippets.append(Passage(
            'notes',
            f"- [{item['category']} / {item['created_at']}] "
            f"{item['content'][:350]}",
            importance=float(item.get('importance') or 0) / 5,
        ))
    for item in episodes:
        snippets.append(Passage(
            'episodes',
            f"- [{item['created_at'][:10]} / {item['role']}] "
            f"{item['content'][:380]}",
            importance=0.5,
        ))
    for item in learned_claims:
        snippets.append(Passage(
            'claims',
            f"- {item['statement']} [{item['state']}; origens: "
            + ', '.join(ref['url'] for ref in item['sources'][:2]) + "]",
        ))
    for item in knowledge:
        snippets.append(Passage(
            'documents',
            f"- {item['title']}: {item['content'][:350]} "
            f"[URL: {item['url']}; {item['evidence_level']}]",
            importance=0.2,
        ))
    from ..living_intelligence import ContinuityEngine
    from ..reflection import ReflectionEngine
    if profile.retrieve_personal:
        continuity = ContinuityEngine(db).context()
        reflection = ReflectionEngine(db).approved_context()
        if continuity:
            snippets.append(Passage('continuity', continuity))
        if reflection:
            snippets.append(Passage('reflection', reflection))
    selected_count = discarded_count = 0
    if profile.name == 'off':
        # A/B baseline: preserve full retrieval in original section order.
        context = unranked_context(snippets)
        selected_count = len(snippets)
    elif profile.retrieve_personal:
        # Conservative character estimate. Reserve capacity for the
        # immutable system prompt, user query and previous turns.
        memory_budget = min(profile.context_limit,
                            max(900, memory_plan.num_ctx * 2 - 4000))
        packed = pack_context(question, snippets, memory_budget)
        context = packed.text
        selected_count, discarded_count = packed.selected, packed.discarded
    else:
        context = ''
    return context, selected_count, discarded_count
