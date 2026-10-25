"""Conservative on-device temporal memory extraction for clearly stated technical settings.

A finite whitelist reduces false associations. Unrecognized statements remain in
six-month conversation history but NEVER become temporal facts automatically.
"""
from __future__ import annotations
import re
import unicodedata
from .privacy import safe_to_capture, safe_to_extract_temporal

# Normalized, nonsensitive keys only. No health, location, financial or personal IDs.
ALIASES = {
    'browser': 'browser', 'navegador': 'browser',
    'sistema operativo': 'sistema_operativo', 'sistema operacional': 'sistema_operativo',
    'distribuicao linux': 'distribuicao_linux', 'distro linux': 'distribuicao_linux',
    'editor': 'editor', 'editor de codigo': 'editor', 'ide': 'editor',
    'linguagem de programacao': 'linguagem_programacao',
    'modelo ollama': 'modelo_ollama', 'modelo de ia': 'modelo_ia',
    'framework frontend': 'framework_frontend',
}
DISPLAY = {
    'browser': 'browser', 'sistema_operativo': 'sistema operativo',
    'distribuicao_linux': 'distribuição Linux', 'editor': 'editor de código',
    'linguagem_programacao': 'linguagem de programação',
    'modelo_ollama': 'modelo Ollama', 'modelo_ia': 'modelo de IA',
    'framework_frontend': 'framework frontend',
}


def norm(s: str) -> str:
    value = unicodedata.normalize('NFD', s.casefold())
    return ' '.join(''.join(ch for ch in value if unicodedata.category(ch)!='Mn').split())


def canonical_subject(raw: str) -> str | None:
    cleaned=norm(raw).strip(' .!?')
    return ALIASES.get(cleaned)


def clean_value(raw: str) -> str | None:
    val=raw.strip().rstrip('.!').strip()
    # One clear assertion; no lists, conditions, quotations or tentative guesses.
    if not (2<=len(val)<=72) or re.search(r'[\n\r?;|<>\[\]{}]',val):
        return None
    if re.search(r'(?i)\b(?:mas|porque|talvez|acho que|se|quando|antes|depois|ou)\b|\s+e\s+',val):
        return None
    if not safe_to_capture(val) or not safe_to_extract_temporal(val):
        return None
    return val


def extract_statement(text: str) -> tuple[str,str] | None:
    """Only positive, explicitly current first-person claims are inferred.

    Examples: 'O meu browser é Brave'; 'O meu browser agora é Firefox';
    'Agora uso Fedora como distribuição Linux'. Past/conditional statements
    cannot change current state. Source text remains available for audits.
    """
    line=text.strip()
    if '?' in line or '\n' in line or len(line)>210:
        return None
    patterns=[
        r'^(?:o meu|a minha)\s+(?P<subject>.+?)\s+(?:agora\s+)?(?:é|e|passou a ser)\s+(?P<value>.+)$',
        r'^agora uso\s+(?P<value>.+?)\s+como\s+(?P<subject>.+)$',
        r'^mudei\s+(?:o meu|a minha)\s+(?P<subject>.+?)\s+para\s+(?P<value>.+)$',
    ]
    for pattern in patterns:
        match=re.match(pattern,line,flags=re.I)
        if match:
            key=canonical_subject(match.group('subject'))
            value=clean_value(match.group('value'))
            if key and value and safe_to_extract_temporal(line):
                return key,value
    return None
