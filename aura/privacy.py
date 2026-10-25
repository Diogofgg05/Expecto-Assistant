"""Conservative automatic capture suppression for obvious credentials.

No filter can identify every secret. Users can always turn recording off and
should not share sensitive data with an unencrypted local prototype.
"""
import re

SENSITIVE = [
    r'(?i)\b(?:password|palavra[ -]?passe|senha|api[ -]?key|chave[ -]?api|token|cvv|cvc|pin)\b\s*[:=]',
    r'(?i)\b(?:o meu|minha|my)\s+(?:password|pin|token|senha|palavra[ -]?passe)\b',
    r'\b(?:\d[ -]*?){13,19}\b',
]

def safe_to_capture(text: str) -> bool:
    return not any(re.search(pattern, text) for pattern in SENSITIVE)

# A deliberately restrictive filter for *automatic knowledge extraction* only.
# Raw conversation capture can be enabled separately. This is not a guarantee
# against all sensitive data; manually review and erase memories when needed.
_EXTRACTION_SENSITIVE = [
    r'(?i)\b(?:morada|endereco|endereço|rua|telefone|telemovel|telemóvel|email|e-mail|iban|nif|numero de contribuinte)\b',
    r'(?i)\b(?:saude|saúde|doença|diagn[oó]stico|medica(?:mento)?|hospital|sintoma|depress[aã]o)\b',
    r'(?i)\b(?:rendimento|sal[aá]rio|d[ií]vida|conta banc[aá]ria|cart[aã]o de cr[eé]dito)\b',
    r'(?i)\b(?:religiao|religi[aã]o|partido politico|partido pol[ií]tico|etnia|orienta[cç][aã]o sexual)\b',
]

# The anchor ensures the excerpt is about the speaker's expressed preference,
# project or durable goal, rather than third parties or a random quoted text.
_EXTRACTION_ANCHORS = [
    r'(?i)\b(?:eu )?(?:prefiro|gosto de|adoro|detesto|quero que|n[aã]o quero|estou a (?:criar|desenvolver|construir)|o meu projeto|a minha preferência|o meu objetivo|tenho como objetivo)\b',
]

def safe_to_extract(quote: str) -> bool:
    if not isinstance(quote,str) or not safe_to_capture(quote):
        return False
    if any(re.search(pattern,quote) for pattern in _EXTRACTION_SENSITIVE):
        return False
    if not any(re.search(pattern,quote) for pattern in _EXTRACTION_ANCHORS):
        return False
    # Disallow fleeting requests misclassified as durable project/goal data.
    if re.search(r'(?i)\b(?:quero que|podes)\s+(?:corrijas|resolvas|expliques|respondas|traduzas|pesquises)\b',quote):
        return False
    return True

# Temporal auto-extraction is narrower than conversational capture.
def safe_to_extract_temporal(text: str) -> bool:
    if not safe_to_capture(text):
        return False
    return not any(re.search(pattern,text) for pattern in _EXTRACTION_SENSITIVE)
