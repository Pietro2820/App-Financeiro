# Arquitetura

## Visão geral de componentes

```
                    ┌─────────────────────┐
                    │   GitHub Actions     │  (cron, Etapa 14)
                    │   (agendado)          │
                    └──────────┬───────────┘
                               │ dispara
                               ▼
┌──────────────────────────────────────────────────────┐
│  backend/app (Python 3.11 + FastAPI)                  │
│                                                         │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │integrations│──▶│   parsers/   │──▶│  services/    │ │
│  │ (gmail.py) │   │ nubank.py    │   │ normalização  │ │
│  │            │   │ inter.py     │   │ + dedupe      │ │
│  └────────────┘   │ bradesco.py  │   └──────┬───────┘ │
│                    └──────────────┘          │         │
│                                               ▼         │
│  ┌────────────┐                     ┌──────────────┐  │
│  │   api/      │◀────────────────── │   models/     │  │
│  │ (REST)      │                    │ (Pydantic +   │  │
│  └─────┬──────┘                     │  SQLAlchemy)  │  │
│        │                            └───────┬───────┘  │
└────────┼────────────────────────────────────┼──────────┘
         │                                     │
         ▼                                     ▼
┌─────────────────┐                 ┌──────────────────────┐
│  PWA (React +    │                 │  Supabase             │
│  Vite + TS)       │◀───────REST────│  (PostgreSQL + RLS +  │
│  Etapa 12+        │                 │   Auth)                │
└──────────────────┘                 └──────────────────────┘
```

## Camadas do backend

- **`integrations/`** — clientes externos (Gmail API). Não sabe nada sobre
  formato de banco específico, só busca e-mails brutos.
- **`parsers/`** — um módulo por instituição, todos implementando a mesma
  interface abstrata (`base.py`). Recebe e-mail bruto, devolve lista de
  transações no modelo normalizado. Testável isoladamente com fixtures.
- **`services/`** — orquestra: chama integrations → parsers → normalização →
  dedupe → persistência. Contém a lógica de negócio (categorização por regra,
  etc).
- **`models/`** — schemas Pydantic (validação/serialização da API) e
  representações de tabela usadas pelo backend.
- **`api/`** — endpoints REST (FastAPI routers), fino, delega tudo para
  `services/`.
- **`core/`** — configuração (env vars), conexão com Supabase, segurança.

## Por que essa separação

O ponto crítico do domínio é: **cada banco manda e-mail num formato
diferente, mas o resto do sistema (dedupe, categorização, dashboard) não
pode saber disso.** Por isso o parser é a única camada que conhece o
formato específico de cada instituição — tudo depois dele trabalha só com
o modelo normalizado de transação. Isso permite adicionar um banco novo
(Etapa 8) sem tocar em `services/`, `api/` ou no frontend.

## Por que Supabase em vez de Postgres + backend próprio de auth

RLS nativo elimina uma classe inteira de bugs de "esqueci de filtrar por
user_id numa query" — a garantia fica no banco, não em cada endpoint.
Auth, migrations versionadas e um client Python oficial (`supabase-py`)
cobrem a maior parte do que precisaríamos construir manualmente.
