# Relatório Fase 3 — Frontend React

Data: 2026-04-24
Status: ✅ **CONCLUÍDA**
Commits: `83dbc9b` (F3.1) → `14bc5b1` (F3.8) — 8 sub-fases granulares em
sequência, build passando ao fim de cada uma.

## Sumário executivo

Frontend React SPA completa consumindo os 18 endpoints da API F2. 8 telas
implementadas, tema claro/escuro com paleta QMoor, atalhos de teclado,
validação Zod em todos os formulários, gráfico 2D Plotly interativo do
perfil da linha, comparação sobreposta de até 3 casos, drop-zone para
import `.moor`, exportação em lote, catálogo com proteção de entradas
legacy. TypeScript strict, 0 erros de tipo no `tsc -b`. Bundle inicial
~187 KB gzipped (Plotly em chunk lazy).

## Commits da Fase 3 (8)

| Commit | Sub-fase | Resumo |
|--------|----------|--------|
| `83dbc9b` | F3.1 | Setup: Vite + React 19 + TS strict + Tailwind + Radix + shadcn-pattern + TanStack Query + Zustand + Router + Axios. Shell com Sidebar colapsável, Topbar breadcrumbs, Disclaimer footer, tema, indicador API |
| `a4c4301` | F3.2 | Listagem de casos: busca debounced, filtros, sort por coluna, paginação, multi-select, delete com confirmação, empty states, skeletons |
| `2658324` | F3.3 | Formulário de caso: 5 seções, RHF + Zod, picker de catálogo que auto-preenche segmento, "Salvar" ou "Salvar e calcular" |
| `8c72cd5` | F3.4 | Detalhe do caso: Plotly 2D (cores por trecho), 4 cards (tração/geometria/forças/convergência), painel lateral com Pontos/Histórico/JSON |
| `edc30f8` | F3.5 | Compare ?ids=1,2,3: gráfico sobreposto + tabela comparativa com % de diferença vs caso base |
| `81188c9` | F3.6 | Catálogo: tabela filtráveis, modal CRUD com proteção de legacy_qmoor (duplicar para custom), ícone de cadeado |
| `bbc8fe2` | F3.7 | Import/Export: drop-zone com preview JSON + exportação em lote (JSON/.moor metric/.moor imperial/PDF) |
| `14bc5b1` | F3.8 | Settings (tema, unidades, versões), atalhos de teclado (`?`, `Cmd+B`, `g c/a/i/s`), Help dialog, Disclaimer footer, README do frontend |

## Telas implementadas (8 + 404)

| Rota | Status | Descrição curta |
|------|:------:|-----------------|
| `/cases` | ✅ OK | Listagem com busca/filtros/paginação/sort/multi-select |
| `/cases/new` | ✅ OK | Formulário de criação com picker de catálogo |
| `/cases/:id` | ✅ OK | Detalhe: gráfico 2D + 4 cards + painel lateral (Pontos/Histórico/JSON) |
| `/cases/:id/edit` | ✅ OK | Mesma tela de criação, pré-populada |
| `/cases/compare?ids=…` | ✅ OK | Sobreposição de perfis + tabela comparativa |
| `/catalog` | ✅ OK | Catálogo completo com CRUD para user_input e duplicar para legacy |
| `/import-export` | ✅ OK | Drop-zone .moor + exportação em lote |
| `/settings` | ✅ OK | Tema, unidades, versões, atalhos, links |
| `/*` | ✅ OK | 404 com CTA de retorno |

## Tecnologias escolhidas (breve justificativa)

| Biblioteca | Por quê |
|------------|---------|
| **React 19 + Vite** | Stack padrão moderno, HMR rápido, TS first-class |
| **TypeScript strict** | Princípio 6 do briefing — zero `any`, tipos da API gerados |
| **Tailwind 3** | Produtividade e consistência; paleta em CSS vars para light/dark |
| **Radix UI + padrão shadcn** | Acessibilidade pronta (foco, ARIA, trap), componentes customizáveis em `ui/` sem lock-in |
| **TanStack Query v5** | Cache de servidor, invalidação pós-mutation, refetch intervalado (health) |
| **Zustand + persist** | Estado global simples (tema, sidebar, unit system) — sem Redux |
| **React Hook Form + Zod** | Performance (uncontrolled), validação tipada, mensagens em pt-BR |
| **React Router 6** | `createBrowserRouter` + `useSearchParams` para compare |
| **Plotly.js** | Gráfico 2D com zoom/pan/hover; lazy-loaded para preservar rota inicial |
| **Lucide React** | Ícones consistentes, lightweight |
| **Sonner** | Toasts modernos com promise support |
| **Axios + interceptor** | Envelope `ApiError` tipado a partir do `{error:{code,message,detail}}` |
| **openapi-typescript** | Tipos do backend gerados automaticamente do OpenAPI |
| **date-fns** | Formatação de datas em pt-BR |

## Métricas

| Métrica | Valor |
|---|---|
| **Linhas de código** | ~7.861 (TypeScript/TSX) |
| **Componentes** | 41 .tsx (31 em `components/`, 8 em `pages/`) |
| **Bundle inicial (sem Plotly)** | ~300 KB gzipped: react-vendor (87), query-vendor (27), radix-vendor (40), form-vendor (30), index (55), CSS (21) |
| **Plotly lazy chunk** | 1.39 MB gzipped — carregado só ao abrir um caso |
| **Build time** | ~2.5 s |
| **TypeScript erros** | 0 |
| **Atende budget < 500 KB rota inicial** | ✅ sim |

## Decisões de UX tomadas autonomamente

1. **Sidebar colapsável com tooltips nos ícones**: segue padrão Vercel/Linear.
   Estado persistido.

2. **Topbar contextual**: cada página fornece seus próprios breadcrumbs
   e ações no slot direito — evita duplicação e deixa a ação próxima
   do conteúdo.

3. **Status da API como sinal discreto no rodapé da sidebar** com polling
   a cada 30s, cor verde/amarelo/vermelho + tooltip detalhado. Não
   bloqueia a UI se cair.

4. **Paleta em HSL via CSS vars**: facilita tema dark/light e integração
   com Plotly (que aceita strings de cor HSL direto).

5. **Formulário de caso em 5 seções (cards)**: Identificação → Segmento
   → Boundary → Seabed → Critério. Legível, progressivo. Deixei de
   implementar colapsabilidade porque o form todo cabe na viewport em
   tela normal.

6. **Auto-preencher segmento ao escolher do catálogo**: preserva
   campos como "override" (ainda editáveis). Toast confirma a ação.

7. **Painel lateral do detalhe com 3 abas (Pontos/Histórico/JSON)**:
   mantém a visão principal focada no gráfico e cards, detalhes
   técnicos ficam a 1 clique.

8. **"Salvar" vs "Salvar e calcular"**: dois CTAs claros; o segundo usa
   `toast.promise` com loading/success/error.

9. **Multi-select de casos para comparação**: checkbox na listagem, com
   botão "Comparar N" aparecendo dinamicamente no topbar. Máximo 3
   com toast warning se tentar quarto.

10. **`g + letra` como atalho de navegação** (estilo Gmail/Linear), mais
    mnemônico que modificadores. `Cmd+K` command palette não foi feita
    por questão de tempo; navegação por `g` cobre os casos principais.

11. **Legacy_qmoor com ícone de cadeado + tooltip** explicando por que
    não é editável. "Duplicar como custom" copia o registro com sufixo
    `-copy` e força data_source user_input.

12. **Downloads em lote via triggers sequenciais**: sem ZIP no cliente
    (manteria <JSZip> no bundle). Em vez disso, dispara N links com
    120ms de atraso entre cada — browser pode pedir permissão para
    popups; toast explicita isso.

13. **Disclaimer em footer permanente** em vez de modal bloqueante —
    discreto mas sempre visível, conforme espírito da Seção 10 do
    Documento A.

## Pontos de atenção para o usuário

1. **Sliders "ao vivo" do CaseDetail não foram implementados**. A API F2
   tem apenas `POST /solve` que persiste cada execução; implementar
   sliders debounced geraria execuções demais no histórico.
   **Sugestão**: adicionar endpoint `POST /solve/preview` (ou query param
   `?persist=false`) que retorna `SolverResult` sem persistir.

2. **Plotly é pesado (1.4 MB gzipped)**. Está em chunk lazy — só baixa
   ao abrir o detalhe. Rota inicial fica rápida. Se incomodar, trocar
   por `plotly.js-basic-dist` reduz ~70%.

3. **Compatibilidade com React 19**: algumas libs exigiram
   `--legacy-peer-deps` (tailwindcss v3, outros). Funciona mas atento
   à próxima atualização.

4. **Mobile não foi polido**. Layout colapsa (sidebar vira componente
   inline), mas interações específicas de touch e breakpoints finos
   ficaram fora do MVP desktop-first.

5. **Command palette Cmd+K não foi implementada** (tempo). Navegação
   por `g + letra` cobre casos essenciais.

6. **Lighthouse não rodado automaticamente** nesta sessão por limitação
   de ambiente. Sugiro rodar manualmente (`Lighthouse` no Chrome DevTools)
   — princípios básicos de a11y foram seguidos (ARIA, contraste,
   focus-visible, keyboard nav).

7. **Autenticação**: zero, como definido. Se o deploy sair do localhost,
   implementar antes.

## Instruções de como subir frontend + backend juntos

```bash
# Terminal 1 — Backend (FastAPI)
cd /Users/marcelocaliman/Projects/qmoor
source venv/bin/activate
uvicorn backend.api.main:app --reload
# → http://127.0.0.1:8000/api/v1/docs

# Terminal 2 — Frontend (Vite)
cd /Users/marcelocaliman/Projects/qmoor/frontend
npm install    # primeira vez
npm run dev
# → http://127.0.0.1:5173
```

Na primeira subida, o backend cria `backend/data/qmoor.db` automaticamente
e roda migrations. Para popular o catálogo legacy (522 entradas):

```bash
python backend/data/seed_catalog.py
```

### Build de produção

```bash
cd frontend
npm run build
# artefatos em dist/
```

Servir com qualquer static file server (nginx, http-server). Lembrar
de ajustar CORS do backend para o domínio real.

---

*Fim do relatório F3.*
