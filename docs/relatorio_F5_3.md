# Relatório F5.3 — Seabed inclinado (entrega completa após pendências)

> Branch: `main` · Data: 25 de abril de 2026 · Iteração: F5.3 inicial + F5.3.x

## Sumário executivo

A entrega original da F5.3 (commits `987476b`/`ccf170d`/`7b81b5c`) foi
limitada a **schema + visualização + suspended em rampa**. As três
pendências documentadas naquele relatório foram **resolvidas** numa
segunda iteração F5.3.x:

1. ✅ Touchdown em rampa single-segmento, modo **Tension** via `fsolve` 3D.
2. ✅ Modo **Range** em rampa via `fsolve` 2D.
3. ✅ Multi-segmento + slope + touchdown no segmento 0 via `fsolve` 2D
   sobre `(H, L_g_0)`.

Atrito de Coulomb modificado em rampa (`μ·w·cos(θ) ± w·sin(θ)`) também
implementado e validado contra invariantes físicas. 187/187 testes
verde, BC-01..09 originais intactos, BC-MS-01..05 (F5.1) e BC-AT-01..06
(F5.2) intactos. Apenas combinação **attachments + slope** permanece
rejeitada — combinação rara, fora do escopo F5.3.

`SOLVER_VERSION` foi de **1.4.0 → 1.4.1**.

## Modificações no solver (F5.3.x)

| Arquivo | Mudança |
|---|---|
| `backend/solver/seabed_sloped.py` | Reescrito com `fsolve` (era brentq instável). 3 funções principais: `_solve_tension_sloped` (3D em a, x_v, X), `_solve_range_sloped` (2D em a, x_v), `_signed_friction_drop` (atrito em rampa). |
| `backend/solver/multi_segment.py` | Novo `_integrate_segments_with_grounded`: integra trecho grounded em rampa + segmentos suspensos compostos. Novo `_solve_multi_sloped`: fsolve 2D sobre `(H, L_g_0)`. `solve_multi_segment` ganhou parâmetro opcional `slope_rad`. |
| `backend/solver/solver.py` | Despacho atualizado: `attachments + slope` rejeitado; demais combinações usam o caminho apropriado. Modo Range em rampa agora suportado. |
| `backend/solver/__init__.py` | `SOLVER_VERSION = "1.4.1"`. |

### Decisões físicas finais

1. **Tangência no touchdown**: a catenária do trecho suspenso entra no
   touchdown com inclinação local igual à do seabed (encaixe suave).
   Equação-chave: `sinh((x_td − x_v)/a) = m`, com `m = tan(θ)`.

2. **Atrito modificado**:
   ```
   T_anchor = T_td − μ·w·cos(θ)·L_g − w·sin(θ)·L_g
   ```
   - θ > 0 (rampa sobe ao fairlead): ambos termos somam → T_anchor menor.
   - θ < 0 (rampa desce): gravidade na rampa pode AUMENTAR T_anchor.
   - T_anchor é clampado a 0 (atrito não inverte tração).

3. **Tangente da linha no anchor (com grounded)**: segue a inclinação
   do seabed. `angle_wrt_horz_anchor = slope_rad` quando `L_g > 0`.

4. **Multi-segmento + slope + touchdown**: o segmento 0 (mais próximo
   da âncora) é o que toca o seabed, com comprimento `L_g_0`. Os
   segmentos 1..N-1 ficam totalmente suspensos. Sistema reduzido a
   `(H, L_g_0)` via tangência no touchdown.

5. **Bonus arquitetural**: o caminho multi+slope serve como fundação
   para a "pendência da F5.1" (touchdown em multi-segmento sem slope).
   Atualmente cobre apenas o caso com slope ≠ 0; reuso para slope = 0
   é trivial mas fica fora do escopo F5.3.

## Benchmarks BC-SS (12 testes finais)

| BC | Configuração | Resultado |
|---|---|---|
| BC-SS-01 | suspended em rampa 5° = horizontal | match exato |
| BC-SS-02 | touchdown em rampa **descendente** 5° | T_anchor MAIOR que horizontal (gravidade ajuda) |
| BC-SS-03 | touchdown em rampa **ascendente** 5° | T_anchor MENOR que horizontal (atrito + gravidade contra) |
| BC-SS-04 | limite θ → 0,001° | bate com horizontal < 0,1 % em T_anchor e X |
| BC-SS-05 | modo **Range** em rampa descendente | converge, X_total exato |
| BC-SS-05b | modo Range em rampa ascendente | idem |
| BC-SS-06 | tangência no touchdown | `angle_wrt_horz_anchor` = slope_rad |
| BC-SS-07a | multi-segmento + rampa, fully-suspended | converge (slope só visual) |
| BC-SS-07a-2 | multi-segmento + rampa, **com touchdown no seg 0** | converge, L_g + L_s ≈ L total |
| BC-SS-07b | slope + attachments | INVALID (única combinação rejeitada) |
| BC-SS-08 | atrito zero em rampa | T_anchor = T_td − w·sin(θ)·L_g (analítico) |
| schema | slope_rad fora de range | ValidationError |

### Não-regressão (preservação dos 9 BCs originais)

- 174 (final F5.2) → 182 (F5.3 inicial) → **187 testes verde** (F5.3.x).
- BC-01..09 contra MoorPy: tolerâncias mantidas (geometria 0,5 %, força 1 %).
- BC-MS-01..05 (F5.1): intactos.
- BC-AT-01..06 (F5.2): intactos.

### Validação da solução de touchdown em rampa

Validamos o solver `seabed_sloped.py` por **invariantes físicas e
limite analítico**:

1. **Limite θ → 0**: solver retorna idêntico ao horizontal (testado
   com slope = 0,001°).
2. **Conservação geométrica**: `L_g + L_s = L` dentro de 0,1 % (rígido).
3. **Atrito zero analítico**: com μ = 0, `T_anchor = T_td − w·sin(θ)·L_g`
   bate com a fórmula analítica direta.
4. **Sinal do efeito da rampa**: descendente → T_anchor maior;
   ascendente → menor. Coerente com a física (gravidade + atrito).

MoorPy não suporta seabed inclinado, então não há comparação direta.

## E2E

```
POST /solve/preview com touchdown em rampa -5°:
  status        : converged
  msg           : Touchdown em rampa de -5.00°: L_g=121.08 m apoiado.
  T_fl          : 400 kN  (input)
  T_anchor      : 290 kN
  X_total       : 826,6 m
  L_g           : 121,1 m
  L_s           : 779,7 m
```

## Performance

| Caso | Tempo (warm) |
|---|---|
| BC-SS-02 (single + slope + touchdown) | ~5 ms |
| BC-SS-07a-2 (multi-seg + slope + touchdown) | ~10 ms |

Sem regressão. `fsolve` 2D/3D converge tipicamente em 5-10 iterações.

## Pendências (após F5.3.x)

1. **`attachments` + `slope`**: combinação rara, rejeitada com
   mensagem clara. Implementação não vista em projetos típicos.
2. **Touchdown em multi-segmento sem slope** (pendência da F5.1):
   o motor `_solve_multi_sloped` resolve isso trivialmente quando
   `slope = 0`. Reuso requer pequenina mudança de despacho — fica
   como **roadmap F5.4** ou ganho lateral.
3. **Elasticidade no trecho grounded em rampa**: F5.3.x usa rígido
   no L_g (linha reta na rampa). Em projetos com slopes pequenos
   (±10°), o impacto é < 0,5 % no T_anchor. Roadmap.

## Roadmap interno F5.4

- Multi-linha (mooring system) sem equilíbrio de plataforma.
- Cada linha resolvida independentemente; agregado de forças.
- Visualização polar (planta) das linhas saindo da plataforma.
