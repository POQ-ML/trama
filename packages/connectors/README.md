# connectors

Contrato de ingestão (`BaseConnector.fetch` / `health_check` + `ConnectorResult`).

- `moodle.py` (`MoodleConnector`): futuramente cursos/turmas/materiais.
- `github_connector.py` (`GitHubConnector`): futuramente repos/commits/PRs.
- `ufc.py` (`UFCConnector`): futuramente dados institucionais UFC.
- `openalex.py` (`OpenAlexConnector`): futuramente works/autores/citações.
- `registry.py`: `ConnectorRegistry` (register/get/list).

Sem dependências externas, sem chamadas reais — métodos levantam `NotImplementedError`.
