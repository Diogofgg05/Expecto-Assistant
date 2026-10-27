"""Expecto 5.2 — explicit-consent, human-curated SFT/DPO dataset exporter.

NO model weight training or reinforcement learning runs here. Train/dev/test are
isolated and never fed into the model automatically. Outputs stay in ignored data/.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path

_ALLOWED = {'sft', 'dpo'}


def _group(prompt: str) -> int:
    norm = re.sub(r'\s+', ' ', prompt.casefold().strip())
    return int.from_bytes(hashlib.sha256(norm.encode('utf8')).digest()[:8], 'big')


def prepare_training_data(examples: list, directory: str | Path, *, format: str,
                          user_authorized: bool = False) -> dict:
    """Create permissioned datasets; never auto-run SFT, DPO or GRPO.

    Sample {
      "prompt": "...", "chosen": "...", "rejected": "..." (only DPO),
      "human_reviewed": true, "contains_personal_data": false,
      "rights": "authorized_for_model_training"
    }
    """
    if not user_authorized:
        raise PermissionError('Exportação exige autorização explícita da pessoa')
    if format not in _ALLOWED or not isinstance(examples, list) or not 3 <= len(examples) <= 500:
        raise ValueError('Formato ou tamanho inválido')
    seen = set()
    prepared = []
    for record in examples:
        if not isinstance(record, dict):
            raise ValueError('Exemplo inválido')
        if (record.get('human_reviewed') is not True
                or record.get('rights') != 'authorized_for_model_training'
                or record.get('contains_personal_data') is not False):
            raise PermissionError('Dados privados, sem revisão humana ou sem direitos explícitos')
        prompt, chosen = record.get('prompt'), record.get('chosen')
        if not isinstance(prompt, str) or not 5 <= len(prompt.strip()) <= 1200:
            raise ValueError('Prompt inválido')
        if not isinstance(chosen, str) or not 1 <= len(chosen.strip()) <= 4000:
            raise ValueError('Resposta escolhida inválida')
        fingerprint = _group(prompt)
        if fingerprint in seen:
            raise ValueError('Prompt duplicado entre conjuntos de avaliação')
        seen.add(fingerprint)
        if format == 'sft':
            item = {'messages': [{'role':'user','content':prompt.strip()},
                                 {'role':'assistant','content':chosen.strip()}]}
        else:
            rejected = record.get('rejected')
            if not isinstance(rejected,str) or not rejected.strip() or len(rejected)>4000 or rejected.strip()==chosen.strip():
                raise ValueError('Preferências DPO inválidas')
            item={'prompt':[{'role':'user','content':prompt.strip()}],
                  'chosen':[{'role':'assistant','content':chosen.strip()}],
                  'rejected':[{'role':'assistant','content':rejected.strip()}]}
        prepared.append((fingerprint, item))
    # Stable partitions, enforced disjointness even for small curated sets.
    ordered=sorted(prepared,key=lambda pair: pair[0])
    partitions={'train':[],'validation':[],'holdout':[]}
    for i, (fingerprint, item) in enumerate(ordered):
        target = 'holdout' if i%10==0 else 'validation' if i%10==1 else 'train'
        partitions[target].append(item)
    # N=3 guarantees one sample in each split, no holdout leakage.
    dest=Path(directory).expanduser()
    if dest.is_symlink() or dest.exists():
        raise FileExistsError('Diretório destino já existe (não substituímos treinos anteriores)')
    dest.mkdir(parents=True,mode=0o700)
    for split,records in partitions.items():
        path=dest/f'{split}.jsonl'
        with path.open('x',encoding='utf-8') as f:
            for item in records:
                f.write(json.dumps(item,ensure_ascii=False)+'\n')
        if os.name != 'nt':
            path.chmod(0o600)
    result={'format':format,'counts':{k:len(v) for k,v in partitions.items()},
            'training_executed':False,'reward_optimization_executed':False,
            'review_required':True,
            'note':'Dados preparados, não treino. Avaliar e aprovar manualmente antes de usar TRL/PEFT.'}
    (dest/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if os.name != 'nt':
        (dest/'manifest.json').chmod(0o600)
    return result
