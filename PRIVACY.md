# Política de Privacidade — App Financeiro Pessoal

Aplicativo pessoal de código aberto (uso exclusivo do proprietário da conta).
Esta página existe para transparência e para atender aos requisitos do
Google OAuth (tela de consentimento).

## 1. Quais dados são processados

- **Tokens OAuth do Gmail** (access/refresh), obtidos via autorização
  explícita do usuário, com escopo mínimo (`gmail.readonly`);
- **Metadados de e-mails** de instituições financeiras: identificador da
  mensagem, remetente, assunto e data de recebimento;
- **Transações normalizadas** extraídas desses e-mails: data, descrição,
  valor e tipo (crédito/débito/transferência);
- **Categorias e regras** criadas manualmente pelo usuário.

## 2. O que NÃO é coletado nem armazenado

- O **corpo completo dos e-mails** nunca é persistido — apenas metadados e
  o payload normalizado + hash (ver `docs/decisions/0001`);
- **Senhas** de bancos ou do Gmail (a autenticação é 100% OAuth 2.0);
- Dados de terceiros: o app só lê caixas de e-mail autorizadas pelo dono.

## 3. Como os dados são protegidos

- Tokens são **criptografados em repouso** (Fernet/AES-128-CBC + HMAC) com
  chave mantida fora do banco de dados (ver `docs/decisions/0002`);
- **Row Level Security** no PostgreSQL: cada usuário enxerga apenas os
  próprios dados;
- A API exige token de autenticação válido em todas as rotas de dados;
- Princípio do menor privilégio em todos os escopos OAuth.

## 4. Onde os dados residem

- Banco de dados: projeto **Supabase** (PostgreSQL gerenciado) de
  propriedade do usuário;
- E-mails: permanecem no **Google/Gmail** — o app apenas os lê via API.

## 5. Compartilhamento

Nenhum dado é vendido, compartilhado com terceiros, usado para publicidade
ou analítica. O processamento existe apenas para o controle financeiro
pessoal do proprietário.

## 6. Exclusão de dados

- **Revogar a conexão Gmail** (rota `/gmail/revoke` ou
  https://myaccount.google.com/permissions) interrompe a coleta e invalida
  os tokens;
- Excluir as linhas/tabelas no projeto Supabase remove os dados
  armazenados;
- E-mails originais permanecem sob controle exclusivo do usuário no Gmail.

## 7. Contato

Pietro Cardoso — pietrocardoso2812@gmail.com

*Projeto pessoal em desenvolvimento. Mudanças nesta política são
versionadas no repositório.*
