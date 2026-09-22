-- =============================================================================
-- Migration 0002: ciclo de vida do token do Gmail + limpeza
-- =============================================================================
-- O access_token do Google expira em ~1h. Para o backend renovar proativamente
-- (sem uma chamada falha antes), precisa saber QUANDO expira.
--
-- Já aplicada manualmente no projeto Supabase em 2026-09-23; este arquivo é a
-- fonte versionada (fonte da verdade = repositório).

alter table gmail_connections
    add column token_expires_at timestamptz;

comment on column gmail_connections.token_expires_at is
    'Expiracao do access_token (hora da conexao/refresh + expires_in do Google). NULL = tratar como expirado.';

-- Atualiza comentarios defasados do 0001: a decisao de criptografia (Fernet na
-- camada de aplicacao) foi tomada na Etapa 3 — ver ADR 0002.
comment on column gmail_connections.access_token_encrypted is
    'Access token cifrado com Fernet (TOKEN_ENCRYPTION_KEY no backend). Nunca em texto plano.';
comment on column gmail_connections.refresh_token_encrypted is
    'Refresh token cifrado com Fernet (TOKEN_ENCRYPTION_KEY no backend). Nunca em texto plano.';

-- Redundante com o indice implicito criado pela constraint
-- unique (user_id, source, external_id) — mesmas colunas, mesma ordem.
-- Mantê-lo só adicionaria overhead de escrita.
drop index if exists idx_transactions_external_id;
