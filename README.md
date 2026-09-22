# App de Controle Financeiro Pessoal

PWA mobile-first que centraliza contas/cartões, importa transações
automaticamente (via e-mail do Gmail) e categoriza gastos.

Veja `docs/architecture.md` para a visão geral de componentes e
`docs/decisions/` para as decisões arquiteturais (ADRs).

## Status

Etapa 1 — estrutura, schema do banco e primeira migration. Gmail, IA,
Open Finance, frontend e automação (GitHub Actions) ainda **não** estão
implementados — isso vem nas próximas etapas.

## Setup (Windows / PowerShell)

### 1. Criar o projeto no Supabase

1. Crie uma conta em https://supabase.com e um novo projeto.
2. Em **Project Settings → API**, copie a **Project URL** e a
   **service_role key** (não a `anon` key — o backend precisa da
   `service_role` para operações administrativas; ela nunca vai para o
   frontend).
3. Copie `.env.example` para `backend/.env` (dentro da pasta `backend/`,
   **não** na raiz do projeto — é de lá que o `uvicorn` roda e lê o
   arquivo) e preencha `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.

### 2. Aplicar a migration do schema

A forma mais simples sem instalar CLI: abra o projeto no Supabase →
**SQL Editor** → cole o conteúdo de
`supabase/migrations/0001_initial_schema.sql` → **Run**. Depois faça o
mesmo com `supabase/seed.sql`.

(Alternativa via CLI, se preferir versionar migrations pelo terminal —
podemos configurar isso numa etapa futura se você quiser.)

### 3. Rodar o backend localmente

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000/health — deve responder
`{"status": "ok", "environment": "development"}`.

Acesse http://127.0.0.1:8000/health/db — deve responder com as 3
instituições do seed (Nubank, Bradesco, Inter). Se isso funcionar, o
schema, a migration e a conexão do backend com o Supabase estão OK.

### 4. Rodar os testes

```powershell
cd backend
pytest
```

### 5. Testar autenticação (Etapa 2)

Ainda não existe tela de login (isso é a Etapa 12), então testamos o
fluxo via `curl` direto contra a API do Supabase Auth, e depois contra
nosso backend.

**Configuração externa antes de testar:**

1. Em **Project Settings → API → JWT Settings**, copie o **JWT Secret**
   e preencha `SUPABASE_JWT_SECRET` no `backend/.env`.
2. Em **Project Settings → API**, copie a chave **anon public** e
   preencha `SUPABASE_ANON_KEY` no `backend/.env` (só usada aqui pra
   testar via curl, o backend em si nunca usa a anon key).
3. Em **Authentication → Providers → Email**, se estiver marcado
   "Confirm email", desmarque temporariamente pra facilitar o teste
   local (sem isso você precisaria clicar num link de confirmação
   enviado por e-mail antes de conseguir logar).

**Criar um usuário de teste** (PowerShell):

```powershell
$SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
$ANON_KEY = "sua-anon-key-aqui"

curl -X POST "$SUPABASE_URL/auth/v1/signup" `
  -H "apikey: $ANON_KEY" `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"teste@example.com\",\"password\":\"senha123456\"}'
```

A resposta traz um `access_token` — copie esse valor.

**Chamar o endpoint protegido do backend:**

```powershell
$TOKEN = "cole-o-access_token-aqui"

curl "http://127.0.0.1:8000/me" -H "Authorization: Bearer $TOKEN"
```

Esperado: `{"user_id": "<uuid do usuário>"}`.

**Sem token** (deve dar 401, não 500):

```powershell
curl "http://127.0.0.1:8000/me"
```

## Estrutura do projeto

Ver árvore completa no prompt original do projeto / `docs/architecture.md`.
