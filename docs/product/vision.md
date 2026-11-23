# Visão do Produto — TRAMA

## 1. Propósito
O **TRAMA** é um Agente de Contexto Acadêmico criado para ajudar estudantes e pesquisadores a organizar projetos, conectar suas fontes de trabalho à literatura científica e acompanhar a evolução desse contexto ao longo do tempo — sempre com **rastreabilidade e controle humano**.

No longo prazo, a plataforma pretende integrar múltiplas fontes acadêmicas (GitHub, OpenAlex, Moodle, fontes públicas institucionais como a UFC e materiais próprios do usuário) em um mapa vivo de relações, mudanças e evidências.

## 2. Princípios do produto
- **Evidência antes de afirmação**: toda relação sugerida deve apresentar trechos literais preservados de ambos os lados (com localização, data de observação e versão/hash), separados da prosa gerada por IA.
- **Transparência epistêmica**: a plataforma trata explicações como hipóteses revisáveis. Quando o contexto é insuficiente, a LLM está indisponível ou não há sustentação semântica, o sistema se abstém ou exibe fallback e ressalvas de forma explícita — sem mascarar falhas como resultados válidos.
- **Memória preservada**: avaliações humanas (*relevante* / *não relevante*), análises históricas e evidências anteriores não são descartadas quando uma fonte muda.
- **Ação explícita do usuário**: cadastrar fontes, iniciar análises, ativar monitoramento e habilitar chamadas a modelos de linguagem são escolhas claras e previsíveis.

## 3. Estado atual (MVP local)
A plataforma já opera de ponta a ponta em ambiente local compartilhado (sem autenticação multiusuário) com o seguinte recorte:

- **Organização por Projetos Acadêmicos**: criação de projetos e agrupamento de fontes em visualização de mapa e lista, além de um feed de mudanças recentes.
- **Fonte GitHub → Literatura OpenAlex**: coleta de metadados normalizados e README de repositórios públicos do GitHub e busca lexical conservadora de artigos relacionados no OpenAlex.
- **Explicação estruturada com evidências**: geração opt-in em português (via Gemini) em quatro blocos (*O que o artigo propõe*, *Relação possível com o projeto*, *Como explorar* e *Limites e incertezas*), acompanhada de fallback textual explícito quando sem LLM.
- **Feedback humano**: classificação de cada sugestão como relevante ou não relevante.
- **Monitoramento contínuo**: worker durável apoiado no PostgreSQL para checagens periódicas das fontes, detecção de alterações de contexto (`stale` / `source_changed`), registro de avisos e suporte a reanálise.

Detalhes operacionais e limites verificados estão documentados em [discovery-runtime.md](../discovery-runtime.md) e [project-navigation.md](../project-navigation.md).

## 4. O que ainda falta para a visão completa
- **Novas fontes e conectores**: implementação real dos conectores Moodle e UFC (hoje apenas interfaces) e suporte a fontes de baixo atrito (artigos por DOI/OpenAlex, notas ou propostas de pesquisa).
- **Contexto mais profundo e busca híbrida**: leitura além do README no GitHub (estrutura e manifestos), busca semântica/híbrida aproveitando `pgvector` e uso do feedback humano para refinar reanálises futuras.
- **Relações entre fontes do projeto**: identificar conexões cruzadas entre diferentes fontes vinculadas ao mesmo projeto acadêmico (não apenas repositório ↔ artigo).
- **Gestão completa e multiusuário**: edição/exclusão de projetos, remoção de fontes, controle da reanálise automática na interface e autenticação com isolamento por usuário/workspace.
