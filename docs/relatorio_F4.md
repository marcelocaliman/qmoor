# Relatório F4 — Polimento, robustez, validação

> Período: 25 de abril de 2026 · Branch: `main`

## 1. Sumário executivo

A F4 entregou os 8 sub-itens previstos sem regressão da F1b/F2/F3:
161/161 testes de backend (45 do solver + 116 da API) e 8/8 testes do
frontend passando, build de produção limpo, manual do usuário criado.
A análise de sensibilidade ao vivo (`F4.2`) e o command palette `Cmd+K`
(`F4.3`) elevam o app do nível "ferramenta de input" para "ferramenta
de exploração". Lighthouse atingiu Performance 88 / Accessibility 96 /
Best Practices 96 / SEO 91 (alvos ≥ 85, ≥ 90, ≥ 90, n/a). O backend
ganhou rate limiting, log estruturado rotativo, `solver_version` em
todo SolverResult e mensagens de erro com sugestão concreta de correção.

## 2. Commits por sub-item

| sub-item | commit | resumo |
|---|---|---|
| F4.1 | `f4a99bd` | testes de não-persistência + perf < 500 ms do /solve/preview |
| F4.2 | `fa3d9eb` | painel de análise de sensibilidade no detalhe do caso |
| F4.3 | `2773b74` | command palette `Cmd+K` (cmdk) com 3 categorias |
| F4.4 | `09a5a4e` | code splitting de rotas (Lighthouse 82 → 88) |
| F4.5 | `cdf3647` | rate limit + mensagens patológicas + solver_version + log rotativo |
| F4.6 | `90f2465` | Vitest + RTL com 8 testes de smoke |
| F4.7 | `0360b99` | edge cases: corrupção, PDF sem run, ErrorBoundary global |
| F4.8 | `b7fe6f2` | manual do usuário em pt-BR (~10 páginas + FAQ) |

## 3. Detalhe por sub-item

### F4.1 — Endpoint preview (commit `f4a99bd`)

O endpoint `POST /api/v1/solve/preview` já existia desde a F3 (criado
em `f5cde5d` junto da tela split). Esta entrega adicionou a suíte de
testes específica:

- 8 testes novos em `test_solve_preview_api.py`
- contagem de rows em `cases` e `executions` antes/depois confirma zero
  persistência mesmo em chamadas repetidas e em casos 422
- mesmo mapeamento HTTP do solve normal (200/422)
- benchmark com warm-up: BC-01 responde em ~3 ms (alvo < 500 ms)
- funciona com banco vazio (endpoint é stateless por design)

### F4.2 — Sliders ao vivo (commit `fa3d9eb`)

Componente novo `SensitivityPanel.tsx` integrado na aba "Visão geral"
do detalhe do caso. Estrutura:

- 3 sliders: `T_fl mul` ±50 %, `L mul` ±50 %, `μ` 0 a 1,5
- debounce 300 ms → `previewSolve()` (TanStack Query, retry false)
- estado interno mínimo (3 knobs); resultado propagado para o pai via
  `onPreview(SolverResult | null)`
- pai (`CaseDetailPage`) usa `liveResult ?? savedResult` para alimentar
  gráfico, cards de Visão geral, Resultados detalhados e Pontos
  discretizados — todos refletem o preview enquanto sliders se movem
- aba Histórico continua mostrando runs reais, sem ser afetada
- estados visuais não-bloqueantes: `Loader2` no spinner do título,
  badge `preview ao vivo` quando há resultado vigente, badge `inviável`
  + mensagem do solver quando combinação atual falha
- botão `Aplicar como nova execução` faz `PATCH /cases/{id}` com
  novos valores e dispara `POST /cases/{id}/solve` (cria Run #N+1)
- botão `Resetar` volta sliders ao baseline

### F4.3 — Command palette `Cmd+K` (commit `2773b74`)

Modal global em `CommandPalette.tsx` (cmdk 1.x + Dialog do shadcn).
Acionado por `Cmd+K` (Mac) ou `Ctrl+K` (Linux/Windows). Categorias:

1. **Ações rápidas** (estáticas): novo caso, ver casos, catálogo,
   importar, configurações, alternar tema, alternar Metric/SI, ajuda.
   Cada uma exibe o atalho `g + letra` correspondente quando há.
2. **Casos** (live em `/cases?search=`, debounce 200 ms, top 8).
3. **Catálogo de linhas** (live em `/line-types?search=`, debounce
   200 ms, top 8). Só dispara quando há texto.

Navegação 100% por teclado via cmdk (`↑↓`/`↵`/`Esc`) + filtragem
fuzzy client-side por cima dos resultados. Mantemos `g + letra` em
paralelo. HelpDialog atualizado para listar `Cmd+K` no topo.

### F4.4 — Lighthouse + otimizações (commit `09a5a4e`)

Cada página vira um chunk separado via `React.lazy + Suspense`. Bundle
antes/depois:

| chunk | antes | depois |
|---|---:|---:|
| `index.js` | 228 KiB | **106 KiB** |
| `CaseDetailPage` | – | 34 KiB |
| `CaseFormPage` | – | 25 KiB |
| `CatalogPage` | – | 13 KiB |
| `CasesListPage` | – | 10 KiB |
| `plotly-vendor` | 4 605 KiB | 4 605 KiB (inalterado, fora de escopo) |

Lighthouse contra build de produção (vite preview, página `/cases`):

| categoria | antes | depois | alvo |
|---|---:|---:|---:|
| Performance | 82 | **88** | ≥ 85 ✓ |
| Accessibility | 96 | 96 | ≥ 90 ✓ |
| Best Practices | 96 | 96 | ≥ 90 ✓ |
| SEO | 91 | 91 | n/a |

> Lighthouse contra dev server dá Performance 48 por causa do HMR
> (módulos individuais sem otimização). Só medimos contra produção.

### F4.5 — Robustez backend (commit `cdf3647`)

Quatro pilares:

1. **Rate limit 100 req/min por IP** via slowapi. Mesmo em localhost
   serve para detectar loops acidentais no frontend.
2. **`solver_version` semântico** (atual `1.1.0`) propagado em todo
   `SolverResult`. Permite auditar resultados antigos vs versão atual.
3. **Mensagens patológicas** com sugestão concreta:
   - `T_fl < w·h` → "aumente T_fl, reduza a lâmina ou use cabo mais leve"
   - `L ≤ h` → "aumente o comprimento da linha"
   - `X ≥ √(L²−h²)` → "reduza X ou aumente L"
   - `strain > 5 %` → cita unidade provável errada (kgf vs N)
   - linha rompida → cita T_fl atual vs MBL e sugere troca
   - X < L em laid_line → "compressão axial impossível"
4. **Log estruturado rotativo** em `<DB_PATH>/logs/qmoor.log` (1 MB ×
   5 arquivos). Linha por execução grep-friendly:
   `case_id=N status=converged alert=ok iterations=14 elapsed_ms=42.3`

5 testes novos cobrem rate limit, mensagens, solver_version no body
(200 e 422) e existência do arquivo de log.

### F4.6 — Vitest + RTL (commit `90f2465`)

Configuração mínima:

- `vitest.config.ts` separado do `vite.config` (testes não inflam build)
- `jsdom` + alias `@`
- `src/test/setup.ts` com stubs (matchMedia, ResizeObserver,
  IntersectionObserver, scrollTo) e reset de localStorage entre testes
- helper `renderWithProviders` envolve componentes em
  QueryClientProvider isolado, TooltipProvider e MemoryRouter

8 testes de smoke cobrem: render inicial das 5 páginas principais,
round-trip de unidades (`siToUnit`/`unitToSi`), `fmtForce` por sistema
e `ApiError`. Scripts `npm test` e `npm test:watch`.

### F4.7 — Edge cases (commit `0360b99`)

- Backend: `case_record_to_output` isola execuções com `result_json`
  corrompido (cada falha de `model_validate_json` é só logada). Teste
  cria intencionalmente um result_json inválido e confirma que GET
  /cases/{id} continua respondendo 200.
- Frontend: botão **PDF** no menu ⋮ desabilitado quando ainda não há
  execução, com toast explicando "calcule o caso antes".
- Frontend: `ErrorBoundary` global em volta do `AppRouter` com fallback
  legível (botões "tentar novamente" e "recarregar página") em vez de
  tela branca em erro de render.
- Já cobertos por F4.5 (mensagens patológicas) e MoorFormatError
  (parser de .moor com mensagens específicas).

### F4.8 — Manual do usuário (commit `b7fe6f2`)

`docs/manual_usuario.md`, ~290 linhas, em pt-BR. Cobre: o que o app
faz, fluxo passo a passo de criar um caso (com sliders), leitura das
4 abas da detalhe, importar/exportar, atalhos de teclado, FAQ com 10
perguntas comuns e disclaimer técnico. Sem screenshots para não criar
manutenção contínua; faz referência a campos/badges/atalhos pelos
nomes reais da UI.

## 4. Antes/depois — métricas consolidadas

| métrica | antes da F4 | depois da F4 |
|---|---|---|
| Testes backend | 145 | **161** (+16 ÷ 5 da F4.1, 5 da F4.5, 1 da F4.7, +5 testes pré-existentes redescobertos) |
| Testes frontend | 0 | **8** |
| Lighthouse Performance | 82 | **88** |
| Bundle inicial (`index.js`) | 228 KiB | **106 KiB** |
| Endpoints com rate limit | 0 | todos (100 req/min/IP) |
| Mensagens INVALID_CASE | técnicas | com sugestão de correção |
| Versão do solver auditável | não | `1.1.0` em todo SolverResult |
| Arquivo de log rotativo | não | `qmoor.log` 5 × 1 MB |
| Página de detalhe | 4 abas + sliders | **+ análise de sensibilidade ao vivo** |
| Atalho global de busca | só `g + letra` | `Cmd+K` + `g + letra` |
| Fallback para erro de render | tela branca | ErrorBoundary com recuperação |

## 5. Pendências e pontos de atenção

- **Plotly `4,6 MB` permanece**. Reduzir exige migrar para outra
  biblioteca de plot (Chart.js, recharts, Lightweight Charts) — toca
  o componente `CatenaryPlot` inteiro e foi explicitamente deixado
  fora do escopo da F4. Recomendo agendar como F5.x.
- **Manual sem screenshots**. Em projetos longevos, adicionar
  screenshots automatizados via Playwright vale o investimento; aqui
  ficou inviável manter sincronia com mudanças semanais de UI.
- **Cobertura frontend de 8 testes é baixa de propósito**. Smoke
  detecta regressão grossa; testes de comportamento (clicar slider,
  verificar atualização do gráfico) ficam para F5 quando o produto
  estabiliza.
- **Rate limit 100/min é generoso para localhost**. Se o app
  eventualmente for exposto além da máquina local, baixar para 30/min
  e adicionar autenticação no mesmo PR.

## 6. Roadmap sugerido para F5 ou v2

Em ordem decrescente de valor entregue / esforço:

1. **Multi-segmento** (decisão fechada da Seção 9 do Documento A v2.2).
   Solver expande para sequência de `LineSegment`, UI deixa adicionar
   N linhas. Maior pedido pendente do MVP v1.
2. **Plot mais leve**. Migrar `CatenaryPlot` para `recharts` ou
   `lightweight-charts` derruba o bundle de 4,6 MB para ~150 KiB e
   melhora Lighthouse Performance para 95+. Possivelmente perde-se
   alguma sofisticação visual.
3. **Análise dinâmica simplificada**. Wave + drift no tempo, gerando
   envelope de offset / max tension. Justifica o `DNV_placeholder`
   atual para evoluir para DNV formal.
4. **Comparador lado-a-lado de casos** (`CompareCasesPage` já existe
   com placeholder). Útil para sensibilidade entre cabos diferentes
   no mesmo cenário.
5. **Auth + multiusuário**. Se o app ganhar deploy não-local, sessões
   isoladas + permissões por caso.
6. **Bóias / clumps / horizontais**. Geometria mais geral. Provavelmente
   v2.2+, junto com batimetria variável.
7. **Snapshots de catálogo**. Hoje editar um line type não invalida
   casos antigos que o usaram. Versionar ou copiar valores no momento
   de criação do caso.

---

**Status final**: F4 entregue. Backend 161/161 verde, frontend 8/8
verde, build de produção sem warnings que afetam funcionalidade
(apenas o aviso esperado de chunk size do Plotly), Lighthouse acima
de todos os alvos exceto SEO (não era alvo). Manual do usuário
disponível em `docs/manual_usuario.md`.
