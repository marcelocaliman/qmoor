# QMoor Web Frontend

Console técnico para análise estática de linhas de ancoragem. Consome a
API REST em `backend/api`. Stack: React 19 + Vite + TypeScript strict +
Tailwind + shadcn-pattern + Radix UI + TanStack Query + Zustand + Plotly.

## Como rodar

Pré-requisito: backend rodando em `http://127.0.0.1:8000`.

```bash
# Na raiz do projeto, em outro terminal:
source venv/bin/activate
uvicorn backend.api.main:app --reload

# No frontend:
cd frontend
npm install
npm run dev
```

Abra [http://127.0.0.1:5173](http://127.0.0.1:5173).

Em dev, `/api/*` é proxificado para `127.0.0.1:8000` (evita CORS).

## Scripts

| Comando | Ação |
|---------|------|
| `npm run dev` | Vite dev server, hot reload |
| `npm run build` | Type-check + build de produção em `dist/` |
| `npm run preview` | Sobe o build de produção local |
| `npm run lint` | ESLint |

## Estrutura

```
src/
├── api/                # Axios client, endpoints tipados, types derivados
│                       # do OpenAPI (openapi-typescript)
├── components/
│   ├── common/         # Logo, ApiStatusIndicator, StatusBadges,
│   │                   # CatenaryPlot, UtilizationGauge, HelpDialog,
│   │                   # LineTypePicker, EmptyState, ThemeToggle
│   ├── layout/         # AppLayout, Sidebar, Topbar, Disclaimer
│   └── ui/             # Primitives shadcn-style (Button, Card, Dialog,
│                       # Select, Tabs, Slider, Popover, Dropdown, …)
├── hooks/              # useDebounce, useKeyboardShortcuts
├── lib/                # utils (cn, fmt*), caseSchema (Zod)
├── pages/              # 8 páginas (lista, detalhe, form, compare,
│                       # catalog, import-export, settings, 404)
├── store/              # Zustand: theme, ui
├── types/openapi.ts    # Gerado a partir do backend
├── Router.tsx          # createBrowserRouter
├── main.tsx            # Entry: providers
└── index.css           # Tailwind + CSS vars (paleta light+dark)
```

## Principais decisões

- **Paleta por CSS vars em HSL**: permite tema light+dark via classe `.dark`
  no `<html>`, tokens compartilhados com Tailwind e Plotly.
- **Radix UI + padrão shadcn** (em `components/ui/`) sem instalar o CLI —
  cada componente é explícito e editável.
- **Tipos da API gerados automaticamente** via `openapi-typescript`. Para
  atualizar quando o backend muda schema:
  `npx openapi-typescript http://127.0.0.1:8000/api/v1/openapi.json -o src/types/openapi.ts`.
- **TanStack Query** gerencia cache de servidor, invalidação pós-mutation,
  refetch no intervalo para `/health`.
- **Zustand com persist** para tema e estado de UI (sidebar collapsed,
  preferência de unidade). Persiste em `localStorage`.
- **Plotly carregado lazy** (Suspense): rota inicial não paga o bundle
  do Plotly (~1.4 MB gzipped) — só ao abrir um caso.
- **Atalhos**: `?` abre ajuda, `Cmd+B` colapsa sidebar, `g c`/`g a`/`g i`/`g s`
  navegam para Casos/Catálogo/Import-Export/Settings.

## Acessibilidade

- ARIA labels em botões de ação sem texto, `role="meter"` no gauge,
  `aria-current="page"` em breadcrumb ativo, `aria-live="polite"` no
  indicador de status da API.
- Todo elemento interativo tem foco visível (Tailwind `focus-visible`).
- Radix primitives já tratam trap de foco em dialogs, combobox, etc.
- Contraste em ambos os temas atende WCAG AA (verificado nas cores
  primárias; componentes derivados herdam).

## Telas implementadas

| Rota | Descrição |
|------|-----------|
| `/cases` | Listagem com busca debounced, filtros (modo/categoria), ordenação por coluna, paginação, multi-select para comparação, delete com confirmação |
| `/cases/new` | Criar caso: 5 seções em cards com validação Zod |
| `/cases/:id` | Detalhe: header + CatenaryPlot + 4 cards (tração/geometria/forças/convergência) + painel lateral com Pontos/Histórico/JSON |
| `/cases/:id/edit` | Reusa o form de criação |
| `/cases/compare?ids=1,2,3` | Gráfico sobreposto + tabela comparativa com % de diferença |
| `/catalog` | Tabela do catálogo com filtros, ações inline, modal para criar/editar/duplicar |
| `/import-export` | Tabs: drop-zone com preview + exportação em lote |
| `/settings` | Tema, sistema de unidades, atalhos, versões |

## Limitações conhecidas (Fase 3)

- **Sliders "ao vivo" do CaseDetail**: backend não tem endpoint de dry-run
  solve; os sliders do briefing não foram implementados (evitamos
  persistir cada ajuste como execução). Workaround futuro: adicionar
  endpoint `POST /solve/preview` que não persiste.
- **Plotly** pesa 1.4 MB gzipped em chunk separado, carregado sob demanda.
  Alternativa menor: `plotly.js-basic-dist`.
- **Mobile** funcional mas não polido (MVP desktop-first).
- **Command palette Cmd+K**: não implementada; atalhos `g + letra` cobrem
  navegação principal.

## Build de produção

```bash
npm run build
```

Artefatos em `dist/`. Servir com qualquer static file server (nginx,
http-server, etc). Em produção, ajuste o CORS do backend para o domínio
real (hoje restrito a `localhost:5173/8000`).
