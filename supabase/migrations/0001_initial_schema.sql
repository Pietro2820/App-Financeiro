-- =============================================================================
-- Migration 0001: Schema inicial do App de Controle Financeiro
-- =============================================================================
-- Convenções:
--   - auth.users é a tabela de usuários do Supabase Auth (não criamos "users").
--   - Toda tabela user-scoped tem RLS habilitado com policy user_id = auth.uid().
--   - financial_institutions e categories "de sistema" (user_id NULL) são
--     catálogos compartilhados: legíveis por todos, editáveis só via migration.
--   - updated_at é mantido automaticamente por trigger (função no fim do arquivo).
-- =============================================================================

create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- -----------------------------------------------------------------------------
-- financial_institutions (catálogo global: Nubank, Bradesco, Inter, ...)
-- -----------------------------------------------------------------------------
create table financial_institutions (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    slug        text not null unique, -- usado pelo parser (ex: 'nubank', 'bradesco')
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table financial_institutions is
    'Catálogo global de instituições financeiras suportadas. Gerenciado via migration/seed, não pelo usuário final.';

-- -----------------------------------------------------------------------------
-- gmail_connections (N:N com instituições via gmail_institution_links)
-- -----------------------------------------------------------------------------
create table gmail_connections (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null references auth.users(id) on delete cascade,
    email_address           text not null,
    -- Tokens NUNCA em texto plano em produção: placeholder aqui, criptografia
    -- (Supabase Vault / pgsodium) é decisão a tomar na Etapa 3 (Gmail OAuth).
    access_token_encrypted  text,
    refresh_token_encrypted text,
    scope                   text not null default 'https://www.googleapis.com/auth/gmail.readonly',
    status                  text not null default 'active' check (status in ('active', 'revoked', 'error')),
    connected_at            timestamptz not null default now(),
    revoked_at              timestamptz,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    unique (user_id, email_address)
);

comment on table gmail_connections is
    'Conexões Gmail do usuário via OAuth2. Um usuário pode ter várias contas Gmail conectadas.';

-- -----------------------------------------------------------------------------
-- gmail_institution_links (N:N: um Gmail pode alimentar várias instituições)
-- -----------------------------------------------------------------------------
create table gmail_institution_links (
    id                      uuid primary key default gen_random_uuid(),
    gmail_connection_id     uuid not null references gmail_connections(id) on delete cascade,
    financial_institution_id uuid not null references financial_institutions(id) on delete cascade,
    user_id                 uuid not null references auth.users(id) on delete cascade,
    created_at              timestamptz not null default now(),
    unique (gmail_connection_id, financial_institution_id)
);

-- -----------------------------------------------------------------------------
-- accounts
-- -----------------------------------------------------------------------------
create table accounts (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    institution_id  uuid not null references financial_institutions(id),
    name            text not null,
    account_type    text not null default 'checking' check (account_type in ('checking', 'savings', 'other')),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- cards
-- -----------------------------------------------------------------------------
create table cards (
    id                  uuid primary key default gen_random_uuid(),
    user_id             uuid not null references auth.users(id) on delete cascade,
    institution_id      uuid not null references financial_institutions(id),
    account_id          uuid references accounts(id) on delete set null, -- opcional
    name                text not null,
    last_four_digits    text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- categories (user_id NULL = categoria padrão do sistema, vinda do seed)
-- -----------------------------------------------------------------------------
create table categories (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid references auth.users(id) on delete cascade, -- NULL = categoria de sistema
    name        text not null,
    color       text,
    icon        text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- transactions (tabela central)
-- -----------------------------------------------------------------------------
create table transactions (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null references auth.users(id) on delete cascade,
    account_id              uuid references accounts(id) on delete set null,
    card_id                 uuid references cards(id) on delete set null,
    institution_id          uuid not null references financial_institutions(id),
    transaction_date        date not null,
    description_original    text not null,
    description_normalized  text not null,
    amount                  numeric(12, 2) not null,
    transaction_type        text not null check (transaction_type in ('credit', 'debit', 'transfer')),
    category_id             uuid references categories(id) on delete set null,
    source                  text not null check (source in ('gmail', 'open_finance', 'manual')),
    external_id             text not null, -- ver ADR 0001 para estratégia de geração
    raw_payload_hash        text,          -- hash do payload normalizado (ver ADR 0001)
    imported_at             timestamptz not null default now(),
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),

    -- Garante idempotência: mesmo usuário + mesma origem + mesmo external_id = 1 transação.
    unique (user_id, source, external_id)
);

-- -----------------------------------------------------------------------------
-- category_rules
-- -----------------------------------------------------------------------------
create table category_rules (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    pattern     text not null, -- keyword ou padrão a buscar na description_normalized
    category_id uuid not null references categories(id) on delete cascade,
    priority    integer not null default 0, -- maior = aplicado primeiro
    active      boolean not null default true,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- import_runs (auditoria de cada execução de importação)
-- -----------------------------------------------------------------------------
create table import_runs (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 uuid not null references auth.users(id) on delete cascade,
    source                  text not null check (source in ('gmail', 'open_finance', 'manual')),
    status                  text not null default 'running' check (status in ('running', 'success', 'partial_failure', 'failed')),
    started_at              timestamptz not null default now(),
    finished_at             timestamptz,
    emails_processed        integer not null default 0,
    transactions_created    integer not null default 0,
    errors_count            integer not null default 0
);

-- -----------------------------------------------------------------------------
-- import_errors
-- -----------------------------------------------------------------------------
create table import_errors (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    import_run_id   uuid references import_runs(id) on delete cascade,
    source          text not null check (source in ('gmail', 'open_finance', 'manual')),
    raw_reference   text,  -- ex: message_id ou hash, nunca o corpo completo do e-mail
    error_type      text not null,
    error_message   text not null,
    stack_trace     text,
    status          text not null default 'pending' check (status in ('pending', 'resolved', 'ignored')),
    created_at      timestamptz not null default now(),
    resolved_at     timestamptz
);

-- =============================================================================
-- Índices para queries frequentes
-- =============================================================================
create index idx_transactions_user_date on transactions (user_id, transaction_date desc);
create index idx_transactions_user_category on transactions (user_id, category_id);
create index idx_transactions_external_id on transactions (user_id, source, external_id);
create index idx_import_errors_user_status on import_errors (user_id, status);
create index idx_category_rules_user_priority on category_rules (user_id, priority desc) where active;

-- =============================================================================
-- Trigger genérico para manter updated_at
-- =============================================================================
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger trg_financial_institutions_updated_at before update on financial_institutions
    for each row execute function set_updated_at();
create trigger trg_gmail_connections_updated_at before update on gmail_connections
    for each row execute function set_updated_at();
create trigger trg_accounts_updated_at before update on accounts
    for each row execute function set_updated_at();
create trigger trg_cards_updated_at before update on cards
    for each row execute function set_updated_at();
create trigger trg_categories_updated_at before update on categories
    for each row execute function set_updated_at();
create trigger trg_transactions_updated_at before update on transactions
    for each row execute function set_updated_at();
create trigger trg_category_rules_updated_at before update on category_rules
    for each row execute function set_updated_at();

-- =============================================================================
-- Row Level Security
-- =============================================================================
alter table financial_institutions enable row level security;
alter table gmail_connections enable row level security;
alter table gmail_institution_links enable row level security;
alter table accounts enable row level security;
alter table cards enable row level security;
alter table categories enable row level security;
alter table transactions enable row level security;
alter table category_rules enable row level security;
alter table import_runs enable row level security;
alter table import_errors enable row level security;

-- financial_institutions: catálogo público de leitura, sem escrita pelo usuário.
create policy "financial_institutions_select_all"
    on financial_institutions for select
    using (true);

-- gmail_connections: só o dono
create policy "gmail_connections_owner_all"
    on gmail_connections for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- gmail_institution_links: só o dono
create policy "gmail_institution_links_owner_all"
    on gmail_institution_links for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- accounts: só o dono
create policy "accounts_owner_all"
    on accounts for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- cards: só o dono
create policy "cards_owner_all"
    on cards for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- categories: dono vê as próprias + as de sistema (user_id is null); só edita as próprias
create policy "categories_select_own_or_system"
    on categories for select
    using (user_id is null or auth.uid() = user_id);

create policy "categories_modify_own"
    on categories for insert
    with check (auth.uid() = user_id);

create policy "categories_update_own"
    on categories for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy "categories_delete_own"
    on categories for delete
    using (auth.uid() = user_id);

-- transactions: só o dono
create policy "transactions_owner_all"
    on transactions for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- category_rules: só o dono
create policy "category_rules_owner_all"
    on category_rules for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- import_runs: só o dono
create policy "import_runs_owner_all"
    on import_runs for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- import_errors: só o dono
create policy "import_errors_owner_all"
    on import_errors for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);
