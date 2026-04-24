# QMoor Web — Briefing para Claude Code

## Contexto

Este é um projeto de aplicação web pessoal para análise estática de linhas de ancoragem offshore. Detalhes completos em `docs/Documento_A_Especificacao_Tecnica_v2_2.docx`.

## Regras importantes

1. **Antes de qualquer tarefa significativa**, consulte `docs/Documento_A_Especificacao_Tecnica_v2_2.docx`. Esse é o briefing técnico definitivo.
2. **Não questione decisões marcadas como "Decisão fechada"** (caixas verdes no documento) sem motivo técnico claro.
3. **Stack:** Python 3.12 (backend), React + Vite + TypeScript (frontend), SQLite (banco), FastAPI (API).
4. **Solver:** catenária elástica com seabed, baseado em SciPy. Validação contra MoorPy (open-source).
5. **Catálogo de materiais:** importado integralmente de `docs/QMoor_database_inventory.xlsx` (522 entradas, 16 tipos).
6. **Unidades internas:** sempre SI (metros, Newtons, kg). Conversões só nas bordas (input/output).
7. **Comunicação:** o usuário não usa terminal. Sempre execute comandos por ele e mostre resultados visualmente.

## Estado atual

- ✅ F0 — Setup do ambiente (concluído)
- ⏳ F1a — Importação do catálogo QMoor para SQLite (próximo passo)
- ⬜ F1b — Implementação do solver
- ⬜ F2 — API FastAPI
- ⬜ F3 — Frontend React
- ⬜ F4 — Calibração com MoorPy
- ⬜ F5 — Polimento e exportações

## Convenções de código

- Backend: type hints obrigatórios, docstrings em funções públicas
- Testes com pytest, casos de benchmark numerados BC-01 a BC-10
- Commits em português, padrão Conventional Commits (feat:, fix:, chore:, docs:, test:)
- Manter assinatura "Co-Authored-By: Claude Opus 4.7" nos commits

## Documentação técnica

- `docs/Documento_A_Especificacao_Tecnica_v2_2.docx` — briefing principal
- `docs/Documento_B_Checklist_Revisor-RESPONDIDO.docx` — respostas técnicas do engenheiro revisor
- `docs/QMoor_database_inventory.xlsx` — catálogo de materiais (fonte de dados)
- `docs/Documentacao_MVP_Versao_2_QMoor.pdf` — documentação original do escopo
- `docs/Cópia de Buoy_Calculation_Imperial_English.xlsx` — fórmulas de boia (uso futuro v2.1)
