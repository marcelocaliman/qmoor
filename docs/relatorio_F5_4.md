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
| F5.4.5a  | Multi-segmento + attachments por linha (reuso de SegmentEditor)     | ✅ |
| F5.4.5b  | Animações + export JSON + Δ vs execução anterior                    | ✅ |
| F5.4.5c  | PDF report (com plan view + tabela de linhas + agregados)           | ✅ |
| F5.4.5d  | Comparação multi-sistema (overlay)                                  | ⬜ |

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

---

## F5.4.5a — entrega (multi-segmento + attachments por linha)

`SegmentEditor` e `AttachmentsEditor` foram generalizados para aceitar
um caminho-base configurável, permitindo reuso integral dentro do form
do mooring system.

### Refactor dos editores

[`SegmentEditor.tsx`](../frontend/src/components/common/SegmentEditor.tsx):

```tsx
export interface SegmentEditorProps<T extends FieldValues = CaseFormValues> {
  index: number
  total: number
  control: Control<T>
  register: UseFormRegister<T>
  watch: UseFormWatch<T>
  setValue: UseFormSetValue<T>
  basePath?: string  // default 'segments'
  onRemove?, onMoveUp?, onMoveDown?
}
```

Mudanças:

- Generic `<T extends FieldValues>` com default `CaseFormValues` — o
  uso existente em `CaseFormPage` continua funcionando sem alteração.
- Helper interno `p(suffix)` que constrói paths como
  `\`${basePath}.${index}.${suffix}\`` com cast `as Path<T>`.
- Todos os `register`, `watch`, `setValue`, `Controller name=` agora
  usam `p(...)` em vez de `\`segments.${index}.x\`` hard-coded.

`AttachmentsEditor` ganhou tratamento simétrico — generic `<T>`,
`basePath?: string` (default `'attachments'`), e `AttachmentRow`
internalizou o helper `p`.

### Form integrado

[`MooringSystemFormPage.tsx`](../frontend/src/pages/MooringSystemFormPage.tsx)
substituiu o form simplificado por linha (1 segmento + boundary)
por:

- **Identidade & posição** (nome, azimuth, raio).
- **Segmentos** — `useFieldArray` em `lines.${idx}.segments` com layout
  flex-wrap reutilizando `<SegmentEditor basePath={\`lines.${idx}.segments\`}>`.
  Multi-segmento, mover up/down, adicionar/remover, e o
  `LineTypePicker` que vem dentro do `SegmentEditor` (com toast e
  preenchimento automático de w/EA/MBL/diâmetro/etc.).
- **Boias e Clumps** — duas instâncias de `<AttachmentsEditor>` lado a
  lado (`kind='buoy'` e `kind='clump_weight'`) sobre o mesmo array
  `lines.${idx}.attachments`.
- **Contorno & ambiente** — h, modo (Tension/Range), input_value, μ.

### Validação

- `npx tsc -b --force` ✅
- `npm run build` ✅ (1.76s)
- `vitest run` ✅ (8 testes)
- Backend `pytest backend/` ✅ (221 testes)

### Decisão

**Cast `as Path<T>` ao construir caminhos via string.** O sistema de
paths do `react-hook-form` aceita strings em runtime; o tipo
`Path<T>` é uma união infinita gerada do schema do form e impossível
de derivar a partir de templates dinâmicos sem conditional types
profundos. O cast confina a perda de checagem ao corpo dos dois
editores; consumidores (`CaseFormPage`, `MooringSystemFormPage`)
continuam totalmente tipados via `<T extends FieldValues>`.

---

---

## F5.4.5b — entrega (animações + export + comparativo)

### Animação do plan view

[`MooringSystemPlanView.tsx`](../frontend/src/components/common/MooringSystemPlanView.tsx)
ganhou classe CSS `msys-animated` aplicada aos elementos que se
movem (linha, fairlead, âncora, label, plataforma, vetor resultante).
Transição: `cx/cy/x1/y1/x2/y2/r/transform 250ms ease-out`. Quando o
usuário ajusta azimuth/raio/T_fl no form ou roda solve, os elementos
deslizam suavemente em vez de "saltar". Sem dependências novas — CSS
puro; navegadores modernos animam atributos SVG geométricos. Safari
pré-17 cai no comportamento antigo (sem animação) sem quebrar nada.

### Export JSON

Backend ([`backend/api/routers/mooring_systems.py`](../backend/api/routers/mooring_systems.py)):

`GET /mooring-systems/{id}/export/json` retorna `MooringSystemOutput`
com `Content-Disposition: attachment` para download direto. Filename
sanitizado para ASCII (`isascii() and isalnum()`) — nomes em pt-BR com
acentos/símbolos (`×`, `é`, etc.) seriam rejeitados pelo header
Latin-1 do HTTP. 2 testes cobrem o feliz path e o 404.

Frontend ([`MooringSystemDetailPage.tsx`](../frontend/src/pages/MooringSystemDetailPage.tsx)):
botão "Exportar JSON" com ícone `Download` no topbar do detail; abre o
endpoint em nova aba (browser baixa via Content-Disposition).

### Δ vs execução anterior

A tabela de histórico ganhou coluna **Δ vs anterior** mostrando a
variação do resultante em kN entre execuções consecutivas. Helper
`<DeltaCell>`:

- `+X` em amarelo com `ArrowUp` quando aumenta (sistema mais carregado)
- `−X` em verde com `ArrowDown` quando diminui (mais relaxado)
- Threshold `< 0.05 kN` mostra `Minus` (estável)
- Última linha (mais antiga, sem anterior) mostra `—`

Útil para auditar evoluções entre runs após o usuário ajustar μ,
boia, etc.

### Validação

- `tsc -b --force` ✅
- `npm run build` ✅ (1.61s)
- `vitest run` ✅ (8 testes)
- `pytest backend/` ✅ (223 testes — +2 da F5.4.2 com export)

---

---

## F5.4.5c — entrega (PDF report)

### `build_mooring_system_pdf`

[`pdf_report.py`](../backend/api/services/pdf_report.py) ganhou função
`build_mooring_system_pdf(msys_rec, execution)` que reusa a infra
existente do `build_pdf` (reportlab + matplotlib em backend `Agg`).
Layout do PDF:

1. **Header** — nome do sistema, id, timestamp, versão do solver.
2. **Disclaimer técnico** — mesmo da Seção 10 do Documento A v2.2,
   reaproveitado da constante `DISCLAIMER`.
3. **Configuração** — tabela com nome, descrição, raio plataforma,
   nº de linhas, id.
4. **Plan view** — `_plan_view_png` desenha matplotlib (com matplotlib
   `Agg` backend) com plataforma circular, linhas radiais coloridas
   por `alert_level`, marcadores de fairlead/anchor, vetor resultante
   rosa (quando há execução). Modo sem execução: âncoras placeholder
   em 4× raio do fairlead.
5. **Resultante agregado** (page break para destaque) — tabela com
   resultante kN/azimuth, n_converged/total, max_utilization, pior
   alerta colorido conforme severidade.
6. **Detalhe por linha** — tabela 8 colunas: nome, Az, R, T_fl/X
   input, H, util, alerta, status.

Sem execução: relatório parcial com configuração + plan view sem
âncoras; mensagem orientando a rodar `/solve`.

### Endpoint

`GET /api/v1/mooring-systems/{id}/export/pdf` retorna `application/pdf`
com `Content-Disposition: attachment` e filename ASCII-safe (mesma
sanitização do export JSON).

### Frontend

Botão **PDF** com ícone `FileText` no topbar do detail, ao lado do
botão JSON. Abre em nova aba; o browser baixa via Content-Disposition.

### Testes

3 testes novos:

- `test_export_pdf_sem_execucao_retorna_pdf_parcial`: gera PDF mesmo
  sem execução; valida magic header `%PDF-` e tamanho > 1 KB.
- `test_export_pdf_com_execucao_inclui_resultados`: após `/solve`,
  PDF tem > 5 KB (plan view + tabelas de resultado).
- `test_export_pdf_id_inexistente_retorna_404`.

Suite total backend: **226 testes verde**.

### Validação

- `tsc -b --force` ✅
- `npm run build` ✅ (1.58s)
- `pytest backend/` ✅ (226 testes)

### Decisão

**`build_mooring_system_pdf` no mesmo arquivo `pdf_report.py`.**
Compartilha `DISCLAIMER`, `_base_table_style`, `_alert_color` e o
boilerplate de Paragraph/Spacer com `build_pdf`. Separar seria mais
DRY mas custaria duplicação de imports e de `getSampleStyleSheet`
boilerplate. Como é uma extensão coesa do mesmo módulo (geração de
relatórios em PDF), mantive junto.

---

## Próximo passo (opcional): F5.4.5d

1. Comparação multi-sistema (overlay de plan views de 2-3 sistemas
   diferentes com legendas).
2. Página de comparação tipo `/mooring-systems/compare?ids=1,2,3`
   reaproveitando o pattern do `CompareCasesPage`.
