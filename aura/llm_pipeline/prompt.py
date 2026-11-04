"""Compose bounded chat turns and unchanged system/identity instructions."""
from __future__ import annotations
from ..identity import Identity, IdentitySettings

def compose_messages(settings, question, history, profile, context, system_prompt, *, input_limit=2000):
    # Legacy placeholders intentionally remain empty; preserve exact prompt spacing.
    continuity_context = reflection_context = ''
    messages = [{'role': 'system', 'content': system_prompt + '\n\n' + Identity().prompt(IdentitySettings(settings.data_dir).mode()) + '\n\n' + context + '\n\n' + continuity_context + '\n\n' + reflection_context}]
    # Bounded rolling history: newest turns remain, old turns are trimmed
    # first. No private prompt/response caching; the system prompt is untouched.
    max_history_chars = 1800 if profile.name == 'fast' else (5200 if profile.name == 'deep' else 3600)
    selected = []
    for x in reversed((history or [])[-8:]):
        if not isinstance(x, dict) or x.get('role') not in ('user', 'assistant') or not isinstance(x.get('content'), str):
            continue
        content = x['content'][:1500]
        if not content:
            continue
        available = max_history_chars - sum(len(item['content']) for item in selected)
        if available < 100:
            break
        selected.append({'role': x['role'], 'content': content[:available]})
    messages.extend(reversed(selected))
    messages.append({'role': 'user', 'content': question[:input_limit]})
    return messages
