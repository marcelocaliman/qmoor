# Relatório F5.4 — Sistema multi-linha (mooring system)

> Iteração atual: **F5.4.1 — schemas + persistência (backend)**

## Escopo da fase

Conforme [roadmap interno do relatorio_F5_3.md](relatorio_F5_3.md#L165-L169):

> Multi-linha (mooring system) sem equilíbrio de plataforma. Cada linha
> resolvida independentemente; agregado de forças. Visualização polar
> (planta) das linhas saindo da plataforma.

Faseamento adotado:

| Slice    | Conteúdo                                                            | Status |
|----------|---------------------------------------------------------------------|--------|
| F5.4.1   | Modelo + persistência (Pydantic, SQLAlchemy, CRUD service, testes)  | ✅ |
| F5.4.2   | Solver dispatcher + agregação de forças + endpoints API + retenção  | ✅ |
| F5.4.3   | BCs de validação adicionais (simetria/equilíbrio, asymm extremos)   | ⬜ |
| F5.4.4   | Frontend: lista + edição + detalhe + plan view polar                | ✅ |
| F5.4.5   | Refinamentos UX: multi-segmento por linha, attachments, animações   | ⬜ |

---

## F5.4.1 — entrega

### Schema Pydantic

[`backend/api/schemas/mooring_systems.py`](../backend/api/schemas/mooring_systems.py)

Dois tipos:

- **`SystemLineSpec`** — uma linha dentro do sistema. Reúne uma definição
  completa de caso (`segments` / `boundary` / `seabed` /
  `criteria_profile` / `user_defined_limits` / `attachments`) acrescida
  das coordenadas polares no plano da plataforma (`fairlead_azimuth_deg`
  ∈ `[0, 360)` e `fairlead_radius` > 0).
- **`MooringSystemInput`** — sistema completo: `name`, `description`,
  `platform_radius`, `lines` (1..16). Validators:
  - Nomes de linha únicos (case-insensitive).
  - Linhas com `criteria_profile=UserDefined` exigem `user_defined_limits`.

Convenção do plano horizontal (documentada na docstring):

> Origem no centro da plataforma. +X = proa (azimuth 0°). Anti-horário
> proa→bombordo→popa. Linha sai radialmente; âncora no prolongamento.

### Persistência

[`backend/api/db/models.py`](../backend/api/db/models.py)

Novo modelo `MooringSystemRecord` segue o padrão de `CaseRecord`: input
completo em `config_json` + colunas desnormalizadas para listagem
(`platform_radius`, `line_count`, `name`, timestamps).

CHECK constraints:
- `length(name) >= 1`
- `platform_radius > 0`
- `line_count >= 1`

Índices: `name` e `updated_at`.

[`backend/api/db/migrations.py`](../backend/api/db/migrations.py) já é
idempotente (`Base.metadata.create_all`) — não precisou de mudança.

### Service CRUD

[`backend/api/services/mooring_system_service.py`](../backend/api/services/mooring_system_service.py)

API mínima (sem router ainda — fica para F5.4.2):

- `create_mooring_system(db, msys_input) -> MooringSystemRecord`
- `get_mooring_system(db, id) -> MooringSystemRecord | None`
- `list_mooring_systems(db, *, page, page_size, search) -> (items, total)`
- `update_mooring_system(db, id, msys_input) -> MooringSystemRecord | None`
- `delete_mooring_system(db, id) -> bool`
- Hidratadores: `mooring_system_record_to_summary` e `mooring_system_record_to_output`.

### Testes

[`backend/api/tests/test_mooring_systems_f5_4_1.py`](../backend/api/tests/test_mooring_systems_f5_4_1.py) — 15 testes verde.

| Categoria | Cobertura |
|-----------|-----------|
| Migration | tabela criada com colunas certas; idempotente; CHECK constraints recusam inválido |
| Pydantic  | aceita payload válido; rejeita nome duplicado, azimuth ≥ 360, raio ≤ 0, lista vazia, UserDefined sem limits |
| CRUD      | round-trip preserva todos os campos; summary omite `config_json`; paginação + busca; update recalcula `line_count`; update id inexistente → None; delete idempotente |

Suite total backend: **206 testes verde** (190 da F5.3.y + 1 já existente desde F5.3.z + **15 desta entrega**).

### Decisões técnicas

1. **Inline vs FK para o caso de cada linha.** Cada `SystemLineSpec`
   tem a definição inline (não FK para `cases`). Motivo: cases existem
   primariamente como sandbox de uma linha isolada e podem ser
   alterados/deletados sem propagar para o sistema. Reusar via "salvar
   como template" pode entrar futuramente sem mudar este schema.

2. **Sem `MooringSystemExecutionRecord` ainda.** Persistência de
   resultados (executions multi-linha + agregados) é da F5.4.2 — fica
   acoplada ao solver dispatcher.

3. **`platform_radius` ≠ `fairlead_radius`.** O primeiro é informativo
   (visualização da plataforma na plan view); o segundo é o raio
   efetivo até o ponto de fixação da linha. Nada impede que sejam
   diferentes (ex.: FPSO com fairleads externos no casco).

4. **JSON pelo `model_dump_json()` do Pydantic.** Mesma estratégia do
   `CaseRecord.input_json`. Round-trip via `model_validate_json()` é
   exato — testado no `test_crud_round_trip`.

---

---

## F5.4.2 — entrega

### Tipos de resultado

[`backend/solver/types.py`](../backend/solver/types.py) ganhou:

- **`MooringLineResult`** — encapsula `SolverResult` + posição polar
  (`fairlead_xy`, `anchor_xy`) + força horizontal sobre o casco
  (`horz_force_xy`).
- **`MooringSystemResult`** — lista de `MooringLineResult` + agregados:
  `aggregate_force_xy`, `aggregate_force_magnitude`,
  `aggregate_force_azimuth_deg`, `max_utilization`, `worst_alert_level`,
  `n_converged`, `n_invalid`, `solver_version`.

### Solver dispatcher

[`backend/solver/multi_line.py`](../backend/solver/multi_line.py) — função
`solve_mooring_system(msys_input)`. Pseudocódigo:

```python
for line in msys.lines:
    res = solver.solve(line.segments, line.boundary, line.seabed, ...)
    θ = radians(line.fairlead_azimuth_deg)
    fairlead_xy = R · (cos θ, sin θ)
    anchor_xy   = (R + X_solver) · (cos θ, sin θ)
    H_xy        = res.H · (cos θ, sin θ)        # 0 se não convergiu
F_total = Σ H_xy_i              # ignora linhas inválidas
```

Convenção: força horizontal sobre a plataforma aponta radialmente para
fora (do fairlead em direção à âncora). Em spread simétrico balanceado,
soma vetorial cancela.

### Persistência (executions)

Nova tabela `mooring_system_executions` em
[`backend/api/db/models.py`](../backend/api/db/models.py):

- FK `mooring_system_id` → `mooring_systems.id` com `ON DELETE CASCADE`.
- `result_json` (MooringSystemResult completo) + desnormalizações:
  `aggregate_force_magnitude`, `aggregate_force_azimuth_deg`,
  `max_utilization`, `worst_alert_level`, `n_converged`, `n_invalid`.
- Índice em `(mooring_system_id, executed_at)`.
- Política de retenção: 10 mais recentes por sistema, truncagem aplicada
  após cada `solve_and_persist`.

### Service

[`backend/api/services/mooring_system_service.py`](../backend/api/services/mooring_system_service.py)
ganhou:

- `solve_and_persist(db, msys_id) -> tuple[record, exec_record] | None`
- `preview_solve(msys_input) -> MooringSystemResult` (sem persistir)
- `_prune_old_executions(db, msys_id)` aplicando retenção de 10
- Hidratação de `latest_executions` em `mooring_system_record_to_output`

### Endpoints REST

[`backend/api/routers/mooring_systems.py`](../backend/api/routers/mooring_systems.py)
montado em `/api/v1`:

| Método  | Rota                                  | Função |
|---------|---------------------------------------|--------|
| GET     | `/mooring-systems`                    | Listar (paginado + busca) |
| POST    | `/mooring-systems`                    | Criar |
| GET     | `/mooring-systems/{id}`               | Detalhar (inclui últimas 10 execuções) |
| PUT     | `/mooring-systems/{id}`               | Atualizar |
| DELETE  | `/mooring-systems/{id}`               | Remover (cascade) |
| POST    | `/mooring-systems/{id}/solve`         | Resolver e persistir |
| POST    | `/mooring-systems/preview-solve`      | Resolver sem persistir (preview UI) |

Tag `mooring-systems` registrada em `main.py` para o OpenAPI.

### Testes

[`backend/api/tests/test_mooring_systems_f5_4_2.py`](../backend/api/tests/test_mooring_systems_f5_4_2.py) — 15 testes verde.

| Categoria          | Cobertura |
|--------------------|-----------|
| Solver puro        | spread simétrico 4× → resultante ≈ 0; assimétrico 2× → magnitude H·√2 a 45°; linha inválida fica fora do agregado; posição radial; alert hierarchy; solver_version propagado |
| Service            | solve_and_persist cria execução com desnormalizações corretas; sistema inexistente → None; retenção de 10 (rodando 12 solves restam 10) |
| API                | POST create → 201; POST /solve → execução persistida + GET vê em latest_executions; 404 em id inexistente; preview não persiste; PUT recalcula line_count; DELETE cascade |

Suite total backend após F5.4.2: **221 testes verde** (206 da F5.4.1 + **15 desta entrega**).

### Decisões técnicas

1. **Força aponta radialmente para fora.** A linha pesa contra a
   plataforma puxando-a em direção à âncora. Em spread balanceado, as
   contribuições cancelam — `aggregate_force_magnitude ≈ 0` é o sinal
   de que o sistema está em equilíbrio com cargas externas zero. Isso
   coincide com a convenção do MoorPy quando a plataforma está na
   posição de offset zero.

2. **Linhas inválidas entram no resultado mas não no agregado.** Se uma
   das N linhas não converge, persistimos a execução com `n_invalid > 0`
   e mantemos as forças das linhas que convergiram. Alternativa
   (rejeitar a execução inteira) seria mais agressiva e impediria a UI
   de mostrar parcialmente o sistema.

3. **`Mz = 0` por construção.** Como cada linha sai radialmente,
   `r_fairlead × F_horz = 0` (vetores paralelos). Não exposto no
   `MooringSystemResult` para não confundir; vira útil só em F5.4 v2+
   se permitirmos linhas tangenciais (ex.: turret com fairleads não
   centrados).

4. **Preview separado de solve.** Mesma lógica de cases: `/preview-solve`
   recebe o input completo e devolve o resultado sem tocar no banco.
   Útil pra UI live (mudar azimuth e ver o resultante atualizar).

---

---

## F5.4.4 — entrega (frontend)

### Componente de plan view

[`frontend/src/components/common/MooringSystemPlanView.tsx`](../frontend/src/components/common/MooringSystemPlanView.tsx)
— SVG nativo (sem Plotly):

- Plataforma como círculo central, marca da proa em +X.
- Eixos cardinais, anéis radiais de referência, grid pontilhado.
- Cada linha como segmento radial fairlead → âncora colorido pelo
  `alert_level` (verde/amarelo/vermelho/cinza-pontilhado para inválido).
- Vetor da força resultante agregada (rosa) saindo do centro com
  comprimento normalizado.
- Modo `previewLines` para edição: desenha a plataforma + fairleads
  mesmo sem resultado de solver, com placeholders de âncora a 4× raio.

### Páginas

| Página                                | Arquivo |
|----------------------------------------|---------|
| Listagem `/mooring-systems`            | [`MooringSystemsListPage.tsx`](../frontend/src/pages/MooringSystemsListPage.tsx) |
| Detalhe `/mooring-systems/:id`         | [`MooringSystemDetailPage.tsx`](../frontend/src/pages/MooringSystemDetailPage.tsx) |
| Criar `/mooring-systems/new`           | [`MooringSystemFormPage.tsx`](../frontend/src/pages/MooringSystemFormPage.tsx) |
| Editar `/mooring-systems/:id/edit`     | mesmo componente, distinguindo via `useParams` |

**Lista**: tabela com nome / line_count / raio plataforma / atualizado +
busca por nome + paginação. Mesmo padrão de `CasesListPage`.

**Detalhe**: plan view do último resultado + card de métricas
agregadas (resultante kN/azimuth, n_converged/total, max_utilization,
worst_alert_level) + tabela de linhas com H/utilização/status + tabela
de histórico de até 10 execuções. Botão "Resolver" que chama
`POST /{id}/solve` e atualiza a query.

**Form**: layout split — esquerda com tabs por linha (cada tab tem
campos de identidade + posição polar + segmento + boundary/seabed);
direita com plan view live + métricas agregadas via `previewSolve`
(debounce 600 ms). "Salvar" e "Salvar e calcular".

### API client

[`frontend/src/api/endpoints.ts`](../frontend/src/api/endpoints.ts) ganhou
seção dedicada com `listMooringSystems`, `getMooringSystem`,
`createMooringSystem`, `updateMooringSystem`, `deleteMooringSystem`,
`solveMooringSystem`, `previewSolveMooringSystem`. Tipos em
[`api/types.ts`](../frontend/src/api/types.ts) reexportam os schemas do
OpenAPI regerado.

### Navegação

Sidebar ganhou item "Mooring systems" (ícone `Compass` da lucide-react)
entre Casos e Catálogo. Router registra as 4 rotas com lazy-load por
chunk separado.

### Decisões de UI

1. **SVG inline em vez de Plotly polar.** Plan view é simples
   geometricamente e não precisa de pan/zoom interativo nesta versão.
   SVG dá controle total sobre estilo (cores por alert level, dash para
   inválidas, vetor resultante customizado) sem o peso do plotly-vendor
   no bundle dessa rota.

2. **Form com 1 segmento por linha.** Iteração inicial — o schema
   suporta multi-segmento, mas a UI só expõe 1 segmento por linha pra
   manter o form gerenciável. F5.4.5 vai trazer multi-segmento +
   attachments + LineTypePicker, reaproveitando `SegmentEditor` da
   `CaseFormPage`.

3. **Preview live com debounce.** Mesmo padrão do `CaseFormPage`:
   `useDebounce(values, 600)` + `useQuery` em
   `previewSolveMooringSystem`. UI mostra spinner durante o cálculo e
   aponta linhas inválidas com aviso vermelho.

### Validação

- `npx tsc -b --force` ✅ (sem erros)
- `npm run build` ✅ (1.67s)

---

## Próximo passo: F5.4.5 — Refinamentos UX

1. Multi-segmento por linha no form (reusar `SegmentEditor`).
2. `LineTypePicker` integrado por linha.
3. Attachments por linha.
4. Animação suave do plan view ao trocar parâmetros.
5. Painel de comparação multi-execução (overlay de plan views).
