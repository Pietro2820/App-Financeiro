# ADR 0002: Criptografia dos tokens do Gmail na camada de aplicação (Fernet)

## Status
Aceito — documenta retroativamente a decisão tomada na Etapa 3 (o comentário
da migration 0001 deixava essa decisão em aberto: "Supabase Vault / pgsodium
é decisão a tomar na Etapa 3").

## Contexto
Os tokens OAuth do Gmail permitem ler **todo o e-mail** do usuário. Vazamento
deles é um incidente de segurança grave, então armazená-los em texto plano
está fora de questão. Opções consideradas:

1. **Texto plano no banco** — rejeitado: qualquer dump/leitura do banco
   (SQL Editor incluído) expõe acesso total às caixas de e-mail.
2. **Criptografia na camada de aplicação** — backend cifra/decifra com
   `cryptography.Fernet` (AES-128-CBC + HMAC-SHA256, à prova de
   adulteração); a chave vive em variável de ambiente (`TOKEN_ENCRYPTION_KEY`).
3. **Criptografia na camada de banco** — Supabase Vault / pgsodium: a chave
   seria gerenciada dentro do próprio Postgres.

## Decisão
Opção **2 (Fernet na camada de aplicação)**:

- Colunas `access_token_encrypted` / `refresh_token_encrypted` guardam só
  ciphertext (texto opaco, prefixo `gAAAAA...`).
- A decifragem acontece apenas em memória, no momento do uso; a API nunca
  retorna tokens — nem cifrados (ver `GmailConnectionOut`).
- A chave nunca toca o banco: `.env` local em dev, GitHub Secrets/Supabase
  secrets em produção.

## Trade-offs
**A favor da opção 2:**
- Simples e portátil: não depende de extensões do banco nem de recursos
  específicos do Supabase.
- Chave separada dos dados: um dump do banco, sozinho, é inútil sem o env.
- Ciphertext opaco até no SQL Editor — proteção contra exposição acidental
  (print de tela, compartilhamento de query).

**Contra / aceites:**
- Gestão da chave é responsabilidade nossa (env + secrets). Perder a
  `TOKEN_ENCRYPTION_KEY` = reautorizar todas as conexões Gmail. Backup dela
  é material crítico.
- Sem rotação de chave implementada. Rotacionar = gerar chave nova +
  reconectar as contas (aceitável para app pessoal mono-usuário; automatizar
  se virar multi-usuário).
- O backend (que tem `service_role` + a chave) pode decifrar — inevitável:
  ele precisa dos tokens para chamar a Gmail API.

A opção 3 (Vault/pgsodium) traria gestão de chave dentro do banco, mas o
backend continuaria precisando de acesso para decifrar — para um app pessoal
mono-usuário, o ganho marginal não paga a complexidade extra. **Revisitar se
o app virar multi-tenant em produção.**

## Consequências
- Testes usam uma chave Fernet dedicada e fixa (`tests/conftest.py`) — sem
  segredos reais no repositório.
- Logs nunca incluem tokens (nem cifrados): ver política "logs sem dados
  financeiros sensíveis".
- `TOKEN_ENCRYPTION_KEY` entra no checklist de segredos de produção
  (Etapa 14: GitHub Actions).
