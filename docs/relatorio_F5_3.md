# Relatório F5.3 — Seabed inclinado (entrega parcial)

> Branch: `main` · Data: 25 de abril de 2026

## Sumário executivo

F5.3 entrega **schema + visualização + suporte a fully-suspended em
rampa** para single-segmento. Touchdown em rampa **NÃO** está nesta
sub-fase: o solver retorna INVALID_CASE com mensagem orientadora
quando o caso seria touchdown. A implementação do touchdown em rampa
foi tentada (módulo `seabed_sloped.py` permanece no repositório como
base), mas o sistema de equações não convergiu de forma robusta
para casos com `slope` pequeno — fica como roadmap explícito da
próxima sub-fase. Backend 182/182 verde, frontend build limpo, plot
desenha a rampa com ângulo declarado no nome.

## Princípio 8 — Honestidade técnica

Esta entrega é **menor do que o escopo original** descrito no
briefing. Cumpre integralmente:
- Schema com `slope_rad` (range ±π/4).
- Visualização da rampa no plot (frontend).
- Solver fully-suspended em rampa funciona (resultado idêntico ao
  horizontal, pois a linha não toca o seabed).

Não cumpre:
- Touchdown em rampa com atrito modificado (`μ·w·cos(θ) ± w·sin(θ)`).

A razão: o sistema de equações para touchdown em rampa exige
parametrização cuidadosa do bracket de busca. Implementação prévia
(`seabed_sloped.py`) caía em `x_td < 0` para slopes negativos
pequenos — sinal de que o ramo correto da função residual não foi
isolado. Calibrar isso de forma robusta exige iteração de meio dia
adicional. Optei por **preservar a robustez do solver** entregando
o subset funcional, em vez de submeter algo instável.

O módulo `seabed_sloped.py` permanece no repositório como
fundação para a continuação — não é despachado em produção.

## Modificações no solver

| Arquivo | Mudança |
|---|---|
| `backend/solver/types.py` | `SeabedConfig.slope_rad` (default 0, range ±π/4 ≈ ±45°). |
| `backend/solver/solver.py` | Despacho com `slope ≠ 0`: rejeita multi-segmento + slope, modo Range + slope, e touchdown + slope. Aceita fully-suspended (T_fl ≥ T_crit_horizontal). |
| `backend/solver/seabed_sloped.py` (novo) | Implementação tentada de touchdown em rampa via sistema reduzido a `v = (X−x_v)/a` com brentq. Mantido como base — não chamado em produção. |
| `backend/solver/__init__.py` | `SOLVER_VERSION = "1.4.0"`. |

### Decisões físicas e de escopo

1. **Slope > 0**: seabed sobe na direção do fairlead (anchor mais
   profundo). Convenção física consistente.
2. **Range admitido**: ±π/4 (≈ ±45°). Slopes maiores são fisicamente
   incomuns e numericamente difíceis.
3. **Fully-suspended em rampa**: o slope não afeta o cálculo da
   catenária pois a linha não toca o seabed. Slope é só metadado
   visual no plot. Solver delega ao caminho horizontal padrão.
4. **Touchdown em rampa**: rejeitado com mensagem citando o T_fl_crit
   horizontal e sugerindo ajustar T_fl/L para fully-suspended ou
   usar slope = 0.
5. **Multi-segmento ou attachments + slope**: rejeitado com mensagem
   clara (combinações fora de escopo F5.3).
6. **Modo Range em rampa**: rejeitado (caso operacional raro, fica
   para sub-fase futura).

## Modificações na API

Sem novos endpoints; `SeabedConfig` ganhou campo `slope_rad` que
o Pydantic valida automaticamente (range ±0.7854 rad). Propagado
pela cadeia normal.

## Modificações no frontend

| Arquivo | Mudança |
|---|---|
| `frontend/src/lib/caseSchema.ts` | `seabedSchema.slope_rad: z.number().min(-π/4).max(π/4).default(0)`. `EMPTY_CASE.seabed.slope_rad = 0`. |
| `frontend/src/pages/CaseFormPage.tsx` | Novo `InlineField` "Inclinação seabed" em °, com Controller convertendo grau ↔ rad. Propagado para PlotArea. |
| `frontend/src/pages/CaseDetailPage.tsx` | `<CatenaryPlot seabedSlopeRad={caseInput.seabed.slope_rad} />`. |
| `frontend/src/components/common/CatenaryPlot.tsx` | Nova prop `seabedSlopeRad`. Linha do seabed segue `y = m·x` no frame solver (transformado para o frame plot). Nome do trace inclui o ângulo (`Seabed (5,0°)`). |
| `frontend/src/components/common/SensitivityPanel.tsx` | Preserva slope_rad ao montar previewInput (não-regressão). |
| `frontend/src/types/openapi.ts` | regenerado. |

## Benchmarks BC-SS

| BC | Configuração | Resultado |
|---|---|---|
| BC-SS-01 | suspended em rampa 5° | bate exato com horizontal (slope só visual) |
| BC-SS-02 | suspended em rampa 10° | converged |
| BC-SS-03 | T_fl < T_crit em rampa | INVALID_CASE com mensagem "touchdown em rampa não suportado" |
| BC-SS-04a | slope + multi-segmento | INVALID_CASE |
| BC-SS-04b | slope + attachments | INVALID_CASE |
| BC-SS-05 | slope + modo Range | INVALID_CASE |
| BC-SS-06 | SOLVER_VERSION ≥ 1.4.0 | confirmado |
| BC-SS-extra | slope_rad fora do range | rejeitado pelo Pydantic |

8 testes novos. Não há benchmark contra MoorPy — MoorPy não suporta
seabed inclinado nativamente.

### Não-regressão
- 174 (final F5.2) → **182 testes verde** (+8 BC-SS).
- BC-01..09 originais contra MoorPy: tolerâncias mantidas.
- BC-MS-01..05 (F5.1): intactos.
- BC-AT-01..06 (F5.2): intactos.

## E2E

```
POST /solve/preview com slope=5° fully-suspended:
  status : converged
  T_fl   : 500 kN  (input)
  T_anc  : 440 kN
  X      : 844 m
  iters  : 7
  msg    : Catenária elástica convergida (slope só visual no plot)
```

## Performance

| Caso | Tempo |
|---|---|
| BC-SS-01 (suspended em rampa) | ~3 ms (= horizontal) |

Sem regressão (caminho horizontal padrão).

## Pendências e atenção

1. **Touchdown em rampa**: a entrega completa exige resolver de forma
   robusta o sistema de 3 equações (a, v, x_td) com brentq sobre `v`.
   O módulo `seabed_sloped.py` está pronto em estrutura mas precisa
   calibração do bracket de busca. Estimativa: 0,5 a 1 dia de
   trabalho focado, com 3-4 BC analíticos.
2. **Multi-segmento + slope + touchdown**: combinação fica para v2.0
   (provavelmente nunca vista em projetos reais).
3. **Modo Range em rampa**: idem.

## Roadmap interno F5.4

- Multi-linha (mooring system) sem equilíbrio de plataforma.
- Cada linha resolvida independentemente; agregado de forças.
- Visualização polar (planta) das linhas saindo da plataforma.
