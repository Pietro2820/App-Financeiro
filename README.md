# App de Controle Financeiro Pessoal

PWA mobile-first que centraliza contas/cartões, importa transações
automaticamente (via e-mail do Gmail) e categoriza gastos.

Veja `docs/architecture.md` para a visão geral de componentes e
`docs/decisions/` para as decisões arquiteturais (ADRs).

## Status

Etapas 1–3 concluídas: estrutura do projeto, schema do banco,
autenticação (Supabase Auth + JWKS) e conexão Gmail via OAuth2.
Próxima: Etapa 4 — leitura de e-mails de teste. IA, Open Finance,
frontend e automação (GitHub Actions) ainda **não** estão implementados.

> ⚠️ Pendência: os arquivos `supabase/migrations/*.sql` e `supabase/seed.sql`
> foram aplicados no projeto Supabase mas ainda não foram commitados neste
> repositório (o schema só existe no banco). Isso será corrigido antes da
> Etapa 4.

## Setup (Windows / PowerShell)

> **Notas Windows (leia antes dos testes com HTTP):**
> 1. Use sempre **`curl.exe`**, nunca `curl` — no Windows PowerShell `curl`
>    é um alias para `Invoke-WebRequest`, cuja sintaxe é incompatível
>    (`-H` falha com erro de conversão para `IDictionary`). O curl real
>    já vem com o Windows 10+. Alternativa 100% nativa: `Invoke-RestMethod`
>    com `-Headers @{ Authorization = "Bearer $TOKEN" }`.
> 2. Variáveis como `$TOKEN`, `$ANON_KEY` e `$SUPABASE_URL` **só existem na
>    janela onde foram definidas** — ao abrir um PowerShell novo, defina-as
>    de novo antes dos comandos.
> 3. O backend precisa estar rodando (`uvicorn`) durante os testes — inclusive
>    quando o navegador chamar o `/gmail/callback` no fluxo OAuth.

### 1. Criar o projeto no Supabase

1. Crie uma conta em https://supabase.com e um novo projeto.
2. Em **Project Settings → API**, copie a **Project URL** e a
   **service_role key** (não a `anon` key — o backend precisa da
   `service_role` para operações administrativas; ela nunca vai para o
   frontend).
3. Copie `.env.example` (raiz do projeto) para `backend/.env` (dentro da
   pasta `backend/`, **não** na raiz — é de lá que o `uvicorn` roda e lê o
   arquivo) e preencha todas as variáveis. Os nomes exatos estão no
   `.env.example` (ex.: a chave secreta do Supabase chama
   `SUPABASE_SECRET_KEY`), junto com os comandos para gerar
   `TOKEN_ENCRYPTION_KEY` e `OAUTH_STATE_SECRET`.

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

1. Nenhuma variável nova no `backend/.env` — a validação do JWT usa
   **JWKS** (chaves públicas buscadas em `{SUPABASE_URL}/auth/v1/...`),
   então o backend não precisa de nenhum segredo do Auth.
2. A chave **anon public** (Project Settings → API) é usada só nos
   comandos `curl` de signup abaixo, direto no terminal — nunca no backend.
3. Em **Authentication → Providers → Email**, se estiver marcado
   "Confirm email", desmarque temporariamente pra facilitar o teste
   local (sem isso você precisaria clicar num link de confirmação
   enviado por e-mail antes de conseguir logar).

**Criar um usuário de teste** (PowerShell):

```powershell
$SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
$ANON_KEY = "sua-anon-key-aqui"

curl.exe -X POST "$SUPABASE_URL/auth/v1/signup" `
  -H "apikey: $ANON_KEY" `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"teste@example.com\",\"password\":\"senha123456\"}'
```

A resposta traz um `access_token` — copie esse valor.

**Chamar o endpoint protegido do backend:**

```powershell
$TOKEN = "cole-o-access_token-aqui"

curl.exe "http://127.0.0.1:8000/me" -H "Authorization: Bearer $TOKEN"
```

Esperado: `{"user_id": "<uuid do usuário>"}`.

**Sem token** (deve dar 401, não 500):

```powershell
curl.exe "http://127.0.0.1:8000/me"
```

### 6. Testar conexão Gmail (Etapa 3)

**Configuração externa (Google Cloud Console):**

1. Crie um projeto em https://console.cloud.google.com e habilite a
   **Gmail API** (APIs & Services → Library).
2. Configure o **OAuth consent screen** (APIs & Services → OAuth consent
   screen). Enquanto estiver em modo **Testing**, só e-mails adicionados
   em *Test users* conseguem autorizar — **e o refresh token expira em
   7 dias**. Para uso contínuo (cron da Etapa 14), publique o app como
   **In production**.
3. Em **Credentials → Create credentials → OAuth client ID**, tipo *Web
   application*, adicione o redirect URI **exatamente** igual ao
   `GOOGLE_REDIRECT_URI` do `backend/.env`
   (ex.: `http://127.0.0.1:8000/gmail/callback`).
4. Preencha `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `backend/.env`.

**Fluxo de teste** (com o backend rodando via `uvicorn`):

```powershell
# 1. Gera a URL de autorização (use o $TOKEN do signup da seção anterior)
curl.exe "http://127.0.0.1:8000/gmail/connect" -H "Authorization: Bearer $TOKEN"

# 2. Abra a "authorization_url" retornada no navegador e autorize.
#    O Google redireciona para /gmail/callback?code=...&state=...
#    Resposta esperada: {"message":"Gmail voce@gmail.com conectado com sucesso."}

# 3. Confira no Supabase (Table Editor → gmail_connections): uma linha com
#    status "active" e tokens criptografados (texto ilegível, começando com "gAAAAA").

# 4. Revogar (connection_id = coluna id da linha acima):
curl.exe -X POST "http://127.0.0.1:8000/gmail/revoke/<connection_id>" `
  -H "Authorization: Bearer $TOKEN"
```

### 7. Ler e-mails do Gmail (Etapa 4)

**Pré-requisitos:** migration `0002` aplicada no Supabase (SQL Editor →
cole `supabase/migrations/0002_gmail_token_lifecycle.sql` → Run) e
**Gmail API habilitada** no projeto do Google Cloud (APIs & Services →
Library → Gmail API → Enable). Conexão Gmail já autorizada (seção 6).

Com o backend rodando e o `$TOKEN` do signup em mãos (PowerShell):

```powershell
# Lista suas conexões (anote o "id"; a resposta nunca inclui tokens)
curl.exe "http://127.0.0.1:8000/gmail/connections" -H "Authorization: Bearer $TOKEN"

# Metadados de e-mails do Nubank — q aceita a sintaxe de busca do Gmail
curl.exe "http://127.0.0.1:8000/gmail/connections/<connection_id>/messages?q=from:nubank.com.br&max_results=5" -H "Authorization: Bearer $TOKEN"
```

Esperado: `{"messages": [{"message_id", "thread_id", "sender", "subject",
"received_at", "label_ids"}, ...], "next_page_token": ...}` — **sem corpo
de e-mail em nenhum lugar**.

Dica de descoberta: `q=newer_than:7d` lista tudo que chegou recentemente —
útil para conferir os remetentes reais de cada banco antes de fixar os
filtros (Etapa 5). Documentação interativa: http://127.0.0.1:8000/docs

Códigos de erro: `404` conexão inexistente/de outro usuário; `409` conexão
revogada ou refresh token morto (refaça o fluxo da seção 6); `422`
parâmetros inválidos (`q` vazio, `max_results` fora de 1–50).

## Estrutura do projeto

Ver árvore completa no prompt original do projeto / `docs/architecture.md`.
