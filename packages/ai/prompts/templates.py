"""Prompt templates — interface, sem chamada real a modelos."""
from __future__ import annotations

TEMPLATES: dict[str, str] = {
    "summarize": "Resuma o contexto:\n{context}",
    "qa": "Pergunta: {question}\nContexto:\n{context}",
    "relate": "Entidades:\n{entities}\nListe relações prováveis.",
}


def render_prompt(name: str, **kwargs: str) -> str:
    """Renderiza um template por nome com `str.format`."""
    template = TEMPLATES.get(name, "")
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
