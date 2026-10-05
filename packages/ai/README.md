# ai

Interfaces puras de IA — sem chamada real a modelos, sem deps externas.

- `context/engine.py`: `ContextEngine` (`build_context`, `summarize`).
- `retrieval/engine.py`: `RetrievalEngine` (`retrieve`).
- `relationships/engine.py`: `RelationshipEngine` (`infer_relationships`).
- `agents/base_agent.py`: `BaseAgent` (`name`, `run`).
- `prompts/templates.py`: templates mínimos + `render_prompt`.
- `evaluation/metrics.py`: `exact_match`, `coverage_ratio` (funções puras).
