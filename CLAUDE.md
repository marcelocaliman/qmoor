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
- ✅ F1a — Importação do catálogo QMoor para SQLite (concluída, 522 entradas)
- ✅ F1b — Implementação do solver (concluída, 45 testes, 96% cobertura, BC-01..09 validados contra MoorPy)
- ✅ F2 — API FastAPI (concluída; ver `docs/relatorio_F2.md`)
- ✅ F3 — Frontend React (concluída; ver `docs/relatorio_F3.md`)
- ✅ F4 — Calibração com MoorPy (concluída; ver `docs/relatorio_F4.md`)
- ✅ F5.1 — Multi-segmento (concluída)
- ✅ F5.2 — Attachments (boias e clumps)
- ✅ F5.3 — Seabed inclinado + batimetria (concluída)
- ✅ F5.4 — Sistema multi-linha (mooring system) — encerrada. Schema + solver dispatcher + frontend completo (lista/detail/form/plan view) + PDF report + comparação multi-sistema. Ver `docs/relatorio_F5_4.md`.

### Documentação de referência (ordem de leitura recomendada)

1. **Este arquivo** (CLAUDE.md) — briefing + decisões fechadas.
2. [`docs/Documento_A_Especificacao_Tecnica_v2_2.docx`](docs/Documento_A_Especificacao_Tecnica_v2_2.docx) — especificação técnica canônica do domínio.
3. [`docs/plano_F2_api.md`](docs/plano_F2_api.md) — desenho da API (schemas SQL, request/response, erros).
4. [`docs/relatorio_F1b.md`](docs/relatorio_F1b.md) — estado e validações do solver.
5. [`docs/auditoria_estrategica_pre_F2.md`](docs/auditoria_estrategica_pre_F2.md) — auditoria pré-F2 (contexto de decisões tomadas).
6. [`docs/Documento_B_Checklist_Revisor-RESPONDIDO.docx`](docs/Documento_B_Checklist_Revisor-RESPONDIDO.docx) — respostas do engenheiro revisor.

Em caso de conflito entre docs: o **Documento A v2.2** é canônico para domínio; este CLAUDE.md registra qualquer override com justificativa (ver seções "Decisões de projeto").

## Decisões de projeto — Fase 1a (catálogo)

Tomadas após inspeção de `docs/QMoor_database_inventory.xlsx` (522 entradas, 16 tipos, 100% imperial, 100% `data_source=legacy_qmoor`). Substituem qualquer ambiguidade da Seção 4.2 do Documento A.

### Rigidez axial EA
- Schema preserva ambas as colunas `qmoor_ea` e `gmoor_ea` (nomes do xlsx mantidos).
- **Default do solver: `qmoor_ea`** — preserva comportamento do QMoor 0.8.5 original, que é o baseline de validação do projeto.
- Cada caso pode sobrescrever via campo `ea_source: "qmoor" | "gmoor"` (default `"qmoor"`).
- Motivação: poliéster exibe razão `gmoor_ea/qmoor_ea` de 10–22× (provável diferença estática vs dinâmica); wires EIPS ~1,45×; correntes ~0,88×. Não há base documental para escolher `gmoor_ea` — portanto default no legado.

### Atrito de seabed — anomalia R5Studless
- `seabed_friction_cf` é uniforme dentro de cada categoria exceto em `StudlessChain`:
  - R4Studless (63 entradas): μ = 1,0
  - R5Studless (41 entradas): μ = 0,6
- **Valores do catálogo preservados sem alteração.** Princípio: não modificar dado legado silenciosamente.
- Anomalia registrada aqui como pendência para validação com o engenheiro revisor.
- Hierarquia de precedência em runtime: solo informado pelo usuário > catálogo da linha (Seção 4.4 do Documento A).

### Primary key e rastreabilidade
- `id INTEGER PRIMARY KEY AUTOINCREMENT` (gerado pelo SQLite).
- **Extensão do schema**: adicionar coluna `legacy_id INTEGER` preservando o id original do xlsx (1–522). Permite auditoria contra o catálogo QMoor e evita colisões quando o usuário adicionar entradas próprias. Entradas criadas pelo usuário têm `legacy_id = NULL`.

### Conversão de unidades na seed
- Todas as 522 entradas estão em imperial — conversão para SI acontece no momento da importação (via Pint).
- `seabed_friction_cf` é adimensional — não converte.
- Armazenamento final: 100% SI (m, N, kg, Pa). `base_unit_system` da entrada reflete unidade **de origem**, não de armazenamento.

### Limpeza do xlsx
- Colunas fantasma do Excel (índices 17–26 sem cabeçalho) são descartadas.
- `comments`, `manufacturer`, `serial_number` estão 100% NULL no catálogo legado; importadas como NULL.

## Decisões de projeto — Fase 1b (solver)

Tomadas durante F1b para resolver situações onde a Seção 3 do Documento A v2.2 era ambígua ou insuficiente. **Todas validadas por benchmarks contra MoorPy** (9/9 BCs dentro das tolerâncias).

### Catenária na forma geral (âncora pode ter V_anchor > 0)
A Seção 3.3.1 do Documento A apresenta equações assumindo âncora no vértice (V_anchor=0). Isso é um caso particular. O BC-01 (T_fl=785 kN) exige V_anchor > 0 — linha quase taut, anchor pull-up acentuado. O solver implementa a **forma geral** parametrizada por `s_a ≥ 0` (arc length do vértice virtual ao anchor), cobrindo tanto V_anchor=0 (touchdown iminente) quanto V_anchor > 0 (fully suspended típico). Ver docstring de [backend/solver/catenary.py](backend/solver/catenary.py).

### Loop elástico via brentq (não ponto-fixo)
A iteração ingênua `L_{n+1} = L·(1 + T̄(L_n)/EA)` **diverge por oscilação** em casos de linha muito taut (L_stretched próximo de √(X²+h²)), notadamente BC-05. Substituído por `scipy.optimize.brentq` sobre `F(L_eff) = L_eff − L·(1+T̄/EA) = 0`, com bracket explícito em limites físicos. Robusto em todos os 45 testes. Ver [backend/solver/elastic.py](backend/solver/elastic.py).

### BCs redefinidos (liberdade da Seção 6.2)
A Seção 6.2 do Documento A listava BC-02/07/08/09 com "entradas a definir". Além disso, **BC-04 e BC-05 com os parâmetros do Documento A são fully suspended, não touchdown** (T_fl_crit ≈ 426 kN < T_fl=1471 kN → sem grounded segment). Rótulo "com touchdown" do BC-04/05 é incorreto. Para ter touchdown real, BC-02/08/09 foram redefinidos com h=300, L=700, T_fl=150 kN, wire rope 3" (T_fl_crit ≈ 194 kN → touchdown garantido). BC-07 com h=100, L=2000, T_fl=30 kN para grande grounded. Documentação detalhada em [docs/relatorio_F1b.md](docs/relatorio_F1b.md) e docstrings dos testes.

### Fallback de bisseção NÃO implementado (divergência vs Documento A)
A Seção 3.5.1 do Documento A menciona "Fallback: bisseção pura se Brent não convergir em 50 iterações" e `SolverConfig.max_bisection_iter=200`. O código usa **apenas brentq** (que internamente já é um método híbrido Brent-Dekker com fallback de bisseção nativo). Como brentq nunca falhou em nenhum dos 45 testes, o fallback manual seria redundante. `max_bisection_iter` foi removido do schema.

### Documento A — changelog v2.3 consolidado
As correções das decisões acima estão consolidadas em [`docs/Documento_A_v2_3_changelog.md`](docs/Documento_A_v2_3_changelog.md) para eventual geração de um novo `.docx`. Até que isso aconteça, o changelog + este CLAUDE.md são as fontes autoritativas das divergências em relação ao v2.2.

## Decisões de projeto — Fase 2 (API e persistência)

Estabelecidas durante a auditoria estratégica pré-F2. Detalhes em [docs/plano_F2_api.md](docs/plano_F2_api.md).

### Autenticação: zero
Aplicação local (localhost). Firewall do macOS protege. Nada de tokens, cookies, basic auth. Se o projeto virar multiusuário, revisitar.

### Formato `.moor` = JSON próprio QMoor-Web
O `.moor` original do QMoor 0.8.5 estava em binário proprietário (`.pyd` do módulo `cppmoor`). Impossível replicar. `.moor` exportado daqui é JSON com schema compatível com a Seção 5.2 do MVP v2 PDF.

### Persistência de execuções
Cada chamada de solve persiste um `execution_record` com timestamp. **Mantém-se as últimas 10 execuções por caso**; mais antigas são truncadas.

### Âncora sempre no seabed (v1)
MVP v1 **rejeita** `endpointGrounded=false` com INVALID_CASE + mensagem. Casos com anchor elevado ficam para v2+.

### Critérios de utilização: 4 perfis disponíveis desde v1
Conforme Seção 5 do Documento A: `MVP_Preliminary` (default, 0.60 MBL), `API_RP_2SK` (intacto 0.60 / danificado 0.80), `DNV` (placeholder; formal só em v3+ com análise dinâmica), `UserDefined`. `SolverResult` retorna `alert_level: ok | yellow | red | broken`.

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
