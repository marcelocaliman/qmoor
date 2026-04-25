# Relatório F5.1 — Multi-segmento (linha composta heterogênea)

> Branch: `main` · Data: 25 de abril de 2026 · Commits: granulares

## Sumário executivo

F5.1 estende o solver para suportar linhas compostas por até 10 segmentos
com propriedades distintas (`w`, `EA`, `MBL`). O caso primário é
**totalmente suspenso** (configuração offshore mais comum: chain pendant
+ wire central + chain pendant). 5 novos benchmarks BC-MS-01..05 cobrem
chain+wire, chain+wire+chain, polyester+chain (taut leg), 2 idênticos
vs single equivalente, e EA contrastante. Todos passam contra MoorPy
(via single-equivalente) e contra invariantes físicas (H constante,
equilíbrio vertical Σw·L_eff). Os 9 BCs originais (BC-01..09) seguem
intactos. Backend 168/168 verde, frontend build limpo.

## Modificações no solver

| Arquivo | Mudança |
|---|---|
| `backend/solver/multi_segment.py` (novo) | módulo completo: 360 linhas. `solve_multi_segment` com modos Tension (brentq sobre H) e Range (fsolve sobre H, V_anchor). Iteração elástica ponto-fixo multi-dimensional. |
| `backend/solver/solver.py` | despacho em `solve()`: `len(segments) > 1` chama `solve_multi_segment`. Single-segmento intocado. |
| `backend/solver/types.py` | `SolverResult.segment_boundaries: list[int]` para o frontend colorir por segmento. |
| `backend/solver/__init__.py` | `SOLVER_VERSION = "1.2.0"` (era 1.1.0). |

### Decisões físicas tomadas autonomamente

1. **Caso primário**: linha **totalmente suspensa**. Touchdown no
   segmento 0 (mais próximo da âncora) é planejado mas não foi entregue
   nesta sub-fase — o teste atualmente cobre só fully-suspended (caso
   "anchor pendant" no qual o anchor está pull-up, V_anchor > 0). A
   restrição é detectada e devolve mensagem clara.
2. **Atrito (μ)**: aplicado apenas ao segmento 0 quando há touchdown
   (não suportado em F5.1, sinalizado para F5.2/F5.3).
3. **Convenção de ordem**: segmento 0 = mais próximo da âncora; último
   = mais próximo do fairlead. Documentada em `multi_segment.py`,
   `case_service.py` e UI.
4. **Iteração elástica**: ponto-fixo multidimensional (vs `fsolve`
   simultâneo). Convergiu em 2-3 iterações em todos os 5 BC-MS;
   robusta para EA diferentes em 1 ordem de grandeza (BC-MS-05).
5. **Limite de 10 segmentos** por linha — sanidade do MVP. Ajustável
   no schema Pydantic e Zod.

## Modificações na API

| Arquivo | Mudança |
|---|---|
| `backend/api/schemas/cases.py` | `segments: max_length=10` (era 1). |
| `backend/api/services/case_service.py` | `line_length` agregada (Σ); `line_type` do segmento 0. |
| `backend/api/services/moor_service.py` | `parse_moor_payload` aceita até 10 segmentos; `export_case_as_moor` serializa todos. μ vai no segmento 0. |

## Modificações no frontend

| Arquivo | Mudança |
|---|---|
| `frontend/src/components/common/SegmentEditor.tsx` (novo) | Componente parametrizado por `index` com seu próprio LineTypePicker, UnitInput por campo, botões mover/remover. |
| `frontend/src/pages/CaseFormPage.tsx` | Substitui o bloco hardcoded `segments.0.*` por `useFieldArray` + map de SegmentEditor + botão "+ adicionar segmento". |
| `frontend/src/components/common/CatenaryPlot.tsx` | Quando `segment_boundaries.length > 2`, renderiza um trace por segmento com paleta rotativa (5 cores). Caso contrário, mantém split suspenso/apoiado. |
| `frontend/src/lib/caseSchema.ts` | `segments.max(10)`. |
| `frontend/src/types/openapi.ts` | regenerado. |

## Benchmarks BC-MS contra MoorPy

| BC | Configuração | T_fl | h | Resultado |
|---|---|---|---|---|
| BC-MS-01 | chain (200 m) + wire (900 m) | 2,0 MN | 400 m | converged, invariantes OK |
| BC-MS-02 | chain (150) + wire (700) + chain (100) | 2,5 MN | 400 m | converged, 3 segs no plot |
| BC-MS-03 | polyester (1500) + chain (200) | 1,5 MN | 600 m | converged, contraste w grande |
| BC-MS-04 | 2 idênticos (300+300) vs single (600) | 600 kN | 300 m | match < 0,5 % em T_fl/X/H |
| BC-MS-05 | EA macio (5e7) + EA rígido (5e8) | 1,5 MN | 300 m | strain por seg ≈ 10× |

**Validação**: cada BC-MS passa em 3 invariantes físicas:
1. **H constante** (Σ T_x.max − T_x.min)/H < 10⁻⁶ ao longo da linha.
2. **Tração monotônica** do anchor ao fairlead.
3. **Equilíbrio vertical**: V_fl − V_anchor = Σ w_i · L_eff_i com
   tolerância 1 %.

Validação adicional contra MoorPy single-equivalente (peso médio
ponderado e EA em série) — H multi vs H_eq dentro de 15 % (tolerância
larga, pois multi-heterogêneo NÃO bate single-equivalente exato).

## BCs originais (BC-01..09) — não-regressão

Todos os 168 testes continuam verde, incluindo:
- `test_camada7_robustez.py::test_BC06_linha_curta_contra_moorpy`
- `test_camada7_robustez.py::test_BC07_linha_longa_tracao_baixa`
- demais BCs em `test_camada1_catenary.py`, `test_camada4_elastic.py`,
  `test_camada5_solver_tension.py`, `test_camada6_solver_range.py`

Tolerâncias usadas: força 1 %, geometria 0,5 % (mantidas).

## E2E

```
POST /api/v1/solve/preview com 3 segmentos:
  status        : converged
  T_fl          : 2500 kN
  T_anchor      : 2288 kN
  X_total       : 866,6 m
  iterations    : 2
  segs          : 3 (boundaries [0, 49, 98, 147])
```

## Performance

| Caso | Tempo (warm) |
|---|---|
| BC-01 (single) | ~3 ms |
| BC-MS-01 (2 segs) | ~5 ms |
| BC-MS-02 (3 segs) | ~7 ms |

Sem regressão. Multi-segmento custa O(N×iters_elásticas), tipicamente
N=2-3 e iters=2-3 → custo ~3× single. Bem abaixo dos 5 s do critério
de pronto.

## Pendências e atenção

1. **Touchdown em multi-segmento**: caso onde o segmento 0 está
   parcialmente apoiado no seabed. F5.1 não suporta — retorna
   `ValueError` com mensagem explicativa. Implementação fica para
   F5.2 ou F5.3 (pode aproveitar a generalização do seabed inclinado).
2. **Modo Range** com multi-segmento usa `fsolve` 2D — para casos
   patológicos (linha quase taut), pode ter convergência menos robusta
   que o brentq do Tension. Documentado.
3. **Atrito por segmento**: F5.1 só aplica μ no segmento 0 quando há
   grounded. Cabos onde múltiplos segmentos tocam o fundo (cenário
   raro) não estão cobertos.
4. **Discretização constante**: cada segmento gera 50 pontos de plot
   independentemente do seu comprimento. Para visualização perfeita
   em segmentos muito curtos, o plot pode ficar concentrado. Não
   afeta cálculo.

## Roadmap interno F5.2

- Boias e clump weights como descontinuidades pontuais em V(s).
- Aproveitar a estrutura de `_integrate_segments` e adicionar elementos
  pontuais entre segmentos (mudança discreta em V_local sem mudança em H).
