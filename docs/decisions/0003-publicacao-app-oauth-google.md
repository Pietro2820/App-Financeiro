# ADR 0003: Modo de publicação do app OAuth — permanecer em Testing

## Status
Aceito — versão revisada em 2026-09-23 (substitui a decisão de publicar tomada
e revertida no mesmo dia, durante a Etapa 4).

## Contexto
O modo **Testing** impõe duas limitações: refresh tokens expiram em **7 dias**
e apenas *test users* (mais a conta dona do projeto, implicitamente) conseguem
autorizar. Para remover a primeira, tentou-se publicar o app (**In production**).
A tentativa revelou três custos não antecipados:

1. **Branding obrigatório completo**: página inicial, política de privacidade,
   *termos de serviço* e domínio autorizado — documentação pública que um app
   pessoal não tem motivo real para manter.
2. **Escopo restritivo sem verificação**: `gmail.readonly` é classificado como
   escopo *restritivo*; app não verificado em produção sofre **bloqueio duro**
   no consentimento (sem a opção "Avançado → Continuar", que existe apenas para
   escopos *sensíveis*). A verificação oficial do Google para escopos
   restritivos exige auditoria de segurança — desproporcional ao caso.
3. **Evidência empírica do modo Testing**: a conta dona do projeto autoriza
   implicitamente; contas externas recebem `403 access_denied` ("fase de
   testes") até entrarem em *Test users* — comportamento observado e
   documentado em `docs/google-cloud-setup.md`.

## Decisão
**Permanecer em Testing**, com todas as contas Gmail do proprietário
cadastradas em **Test users** (limite: 100 contas por ciclo de vida do app —
folgado para uso pessoal). Não publicar; não buscar verificação.

## Consequências e mitigações
- **Refresh tokens expiram em 7 dias.** O sistema já trata o sintoma sem
  falhar silenciosamente: `invalid_grant` → conexão `status='error'` + API
  responde 409 com mensagem acionável ("reconecte"). Reconexão semanal é
  custo aceito para o MVP; Etapa 15 avalia alerta proativo de expiração.
  (Nota: em Testing o prazo conta da concessão; usar o token não o renova —
  portanto não existe "keep-alive" por cron, apenas reconexão.)
- **Toda conta Gmail nova** precisa ser adicionada em *Test users* antes de
  conectar — passo documentado no guia de setup.
- **Revisitar se**: o app deixar de ser mono-usuário; a reconexão semanal se
  tornar insustentável na automação (Etapa 14); ou surgir fonte alternativa
  que dispense Gmail (Open Finance, Etapa 17).
