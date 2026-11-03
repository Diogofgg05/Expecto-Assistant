"""Validate model discovery before selecting a local inference backend."""


def installed_models(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('models'), list):
        raise ValueError('Invalid Ollama model list')
    if len(payload['models']) > 1000:
        raise ValueError('Model list exceeds discovery budget')
    result = {}
    for item in payload['models']:
        if not isinstance(item, dict):
            raise ValueError('Invalid model entry')
        name, digest = item.get('name'), item.get('digest')
        if not isinstance(name, str) or not name.strip() or len(name) > 256:
            raise ValueError('Invalid model name')
        if digest is not None and (not isinstance(digest, str) or len(digest) > 256):
            raise ValueError('Invalid model digest')
        if name in result and result[name] != digest:
            raise ValueError('Conflicting model identities')
        result[name] = digest
    return result
