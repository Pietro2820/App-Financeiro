# Setup do Google Cloud (Gmail API + OAuth 2.0)

Guia completo para criar (ou recriar) o projeto do Google Cloud que dá
poder ao backend de ler e-mails via OAuth. Para o racional das decisões,
ver `docs/decisions/0003-publicacao-app-oauth-google.md`.

> **Regra de ouro:** se o projeto já existe e funciona, NÃO recrie.
> Recriar client ID/secret invalida os refresh tokens guardados no banco e
> obriga reconectar todas as contas Gmail.

## 1. Criar o projeto

1. https://console.cloud.google.com (qualquer conta Google sua — a conta
   "dona" do projeto não precisa ser a que vai conectar o Gmail)
2. Seletor de projeto no topo → **New Project** → nome `app-financeiro` →
   **Create** → selecione-o no seletor.

## 2. Habilitar a Gmail API

Menu ☰ → **APIs & Services → Library** → busque **Gmail API** → **Enable**.

> Sem isso o OAuth funciona, mas `messages.list`/`messages.get` retornam
> 403 — armadilha que custou debug na Etapa 4.

## 3. Configurar a tela de consentimento

Menu ☰ → **Google Auth Platform** (nome atual; em consoles antigos:
*APIs & Services → OAuth consent screen*):

- **Branding**: User Type **External**; nome do app; e-mail de suporte;
  página inicial (ex.: o repositório público); **URL de política de
  privacidade pública** (este projeto usa `/PRIVACY.md` no GitHub — o campo
  é obrigatório para publicar o app).
- **Data Access (escopos)** — exatamente os que o código pede:
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/userinfo.email`
  - `openid`
- **Audience**: em modo Testing, só contas listadas em *Test users*
  autorizam. Após publicar (ADR 0003), essa lista deixa de importar.

## 4. Criar o client OAuth

**Google Auth Platform → Clients** (ou *APIs & Services → Credentials*) →
**+ Create Credentials → OAuth client ID**:

- Application type: **Web application**
- **Authorized redirect URIs**: `http://127.0.0.1:8000/gmail/callback`
  — idêntico, caractere por caractere, ao `GOOGLE_REDIRECT_URI` do
  `backend/.env` (protocolo, porta, caminho, sem barra final)
- **Create** → copie **Client ID** e **Client Secret**.

## 5. Configurar o backend

No `backend/.env` (nunca commitar):

```
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/gmail/callback
```

Em produção/automação (Etapa 14), esses valores vivem em GitHub Secrets.

## 6. Testar

Com o backend rodando e um `$TOKEN` de usuário válido:

```powershell
$url = (Invoke-RestMethod "http://127.0.0.1:8000/gmail/connect" -Headers @{ Authorization = "Bearer $TOKEN" }).authorization_url
Start-Process $url
```

Autorize no navegador; o Google redireciona para o callback e a página
mostra `{"message":"Gmail ... conectado com sucesso."}`. Confira em
`GET /gmail/connections` (sem tokens na resposta) e no Supabase:
`select email_address, status, left(refresh_token_encrypted,10) from gmail_connections;`
— o prefixo `gAAAA` confirma ciphertext Fernet (ADR 0002).

## Armadilhas conhecidas

| Sintoma | Causa |
|---|---|
| 403 `PERMISSION_DENIED` na leitura | Gmail API não habilitada (passo 2) |
| `redirect_uri_mismatch` no consent | URI do client ≠ `GOOGLE_REDIRECT_URI` |
| `403 access_denied` "fase de testes" | Conta fora de *Test users* — a conta
dona do projeto entra implicitamente; as demais precisam de cadastro |
| "Acesso bloqueado ... verificação" | App não verificado pedindo escopo
restritivo (`gmail.readonly`) — ver ADR 0003 (permanecemos em Testing) |
| Refresh morrendo após 7 dias | Comportamento do modo Testing (ADR 0003);
o backend marca a conexão `error` + 409 acionável |
