# ADR 0001: Estratégia de deduplicação de transações

## Status
Aceito

## Contexto
Um mesmo e-mail pode ser reprocessado (reexecução do cron, reconexão do Gmail,
reimportação manual). Precisamos garantir que a mesma transação nunca seja
inserida duas vezes, mesmo quando:

1. O mesmo e-mail é processado mais de uma vez.
2. Um único e-mail contém múltiplas transações (ex: fatura com várias compras).
3. O usuário reimporta manualmente (CSV) algo que já veio do Gmail.

## Decisão

**Chave de deduplicação:** `(user_id, source, external_id)` — constraint `unique`
na tabela `transactions`.

- **Fonte Gmail:** `external_id = message_id` do Gmail quando o e-mail tem
  exatamente 1 transação. Quando o e-mail contém N transações,
  `external_id = "{message_id}-{index}"`, onde `index` é a posição da
  transação dentro do e-mail (0-based), determinística pela ordem de
  extração do parser.
- **Fonte manual (CSV etc.):** `external_id` é um hash SHA-256 dos campos
  `(data, valor, descrição_original, conta)`. Isso não é 100% à prova de
  colisão para lançamentos manuais idênticos no mesmo dia — aceitável para
  o MVP, revisitar se virar problema real.
- **`raw_payload_hash`:** hash do **payload já normalizado** (não do e-mail
  bruto). Motivo: se o banco mudar só o texto de marketing do e-mail mas o
  conteúdo financeiro (data/valor/descrição) permanecer igual, não queremos
  marcar como "alterado". O hash do bruto geraria falsos positivos a cada
  mudança de template do banco. Trade-off: não detectamos mudança de
  template automaticamente — isso é responsabilidade do parser falhar
  explicitamente (ver `import_errors`) quando não conseguir extrair os
  campos esperados.

## Fluxo de inserção
1. Parser extrai transação(ões) normalizada(s) do e-mail.
2. Para cada transação, calcula `external_id` conforme regra acima.
3. Tenta `INSERT ... ON CONFLICT (user_id, source, external_id) DO NOTHING`.
4. Se houve conflito (0 linhas afetadas) → log informativo "duplicata
   ignorada" em `import_runs`, não é erro.
5. Se falhou por outro motivo → grava em `import_errors`.

## Consequências
- Reexecutar o cron é sempre seguro (idempotente).
- Precisamos que o parser seja determinístico na ordem de extração das
  transações dentro de um e-mail multi-transação — testar isso explicitamente
  nos testes unitários do parser (fixture com e-mail multi-transação).
