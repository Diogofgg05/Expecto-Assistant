"""Note CRUD, indexing, encrypted backup and export.

Unrecognized commands return None for deterministic dispatch fallthrough.
"""
from __future__ import annotations
import re
from ..security import VaultError


async def handle_note_commands(engine, original: str, key: str, respond):
    m = re.match(r'^(?:procura|pesquisa|encontra) (?:na )?memoria (?:sobre )?(.+)$', key)
    if m:
        query = original[original.casefold().find(m.group(1)):] if m.group(1) in original.casefold() else m.group(1)
        matches = await engine.memory.recall(query, 20)
        return respond(f'Encontrei {len(matches)} memórias relacionadas.' if matches else
                     'Não encontrei memórias relacionadas.',
                     action={'type':'open', 'panel':'memory'}, data=matches)

    m = re.match(r'^(?:corrige|atualiza) (?:a )?(?:memoria|nota) ([a-f0-9]{12}) (?:para|com) (.+)$', key)
    if m:
        original_match = re.match(r'^(?:corrige|atualiza) (?:a )?(?:mem[oó]ria|nota) [a-f0-9]{12} (?:para|com) (.+)$', original, re.I)
        new_content = original_match.group(1) if original_match else m.group(2)
        updated = await engine.memory.correct(m.group(1), new_content)
        return respond('Atualizei a memória e preservei o histórico da correção.' if updated else
                     'Não encontrei essa memória.',
                     action={'type':'open', 'panel':'memory'}, data=engine.db.memories())

    if key in ('indexa as memorias', 'atualiza o indice da memoria'):
        result = await engine.memory.index_pending()
        return respond(f"Indexei {result['indexed']} memórias. Por indexar: {result['pending']}. {result['reason']}")

    if key in ('faz backup da memoria', 'cria copia de seguranca da memoria'):
        try:
            target = engine.secure_backups.create_backup()
            return respond('Criei uma cópia de segurança CIFRADA em '+str(target)+
                         '. Guarda a frase-passe separadamente: sem ela não é possível restaurar.')
        except (VaultError, OSError) as exc:
            return respond('Não criei backup. '+str(exc))

    if key in ('exporta a memoria', 'exporta as minhas memorias'):
        try:
            target = engine.secure_backups.export_memory(engine.settings.episodic_lookback_months)
            return respond('Exportei a memória CIFRADA em '+str(target))
        except (VaultError, OSError) as exc:
            return respond('Não exportei a memória. '+str(exc))

    m = re.match(r'^(?:lembra[ -]te de|guarda na memoria|memoriza)\s+(.+)$', key)
    if m:
        # Use original case/accents of note, not normalized version.
        prefix = re.match(r'^(?:lembra[ -]te de|guarda na mem[oó]ria|memoriza)\s+', original, re.I)
        note = (original[prefix.end():] if prefix else m.group(1)).strip()
        if len(note) < 3:
            return respond('A nota é demasiado curta para guardar.')
        item = await engine.memory.remember(note)
        return respond('Guardei essa informação na tua memória local.',
                     action={'type': 'open', 'panel': 'memory'},
                     data=engine.db.memories())

    m = re.match(r'^(?:esquece a (?:nota|memoria)|apaga a nota)\s+([a-f0-9]{12})$', key)
    if m:
        deleted = engine.db.delete_memory(m.group(1))
        return respond('Nota eliminada.' if deleted else 'Não encontrei essa nota.',
                     action={'type': 'open', 'panel': 'memory'}, data=engine.db.memories())

    return None
