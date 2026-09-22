-- Categorias padrão do sistema (user_id = NULL) e instituições iniciais.
-- Rode depois da migration 0001. Ajuste/expanda conforme necessário.

insert into financial_institutions (name, slug) values
    ('Nubank', 'nubank'),
    ('Bradesco', 'bradesco'),
    ('Inter', 'inter')
on conflict (slug) do nothing;

insert into categories (user_id, name, color, icon) values
    (null, 'Alimentação', '#F59E0B', 'utensils'),
    (null, 'Transporte', '#3B82F6', 'car'),
    (null, 'Moradia', '#8B5CF6', 'home'),
    (null, 'Saúde', '#EF4444', 'heart-pulse'),
    (null, 'Lazer', '#10B981', 'gamepad'),
    (null, 'Compras', '#EC4899', 'shopping-bag'),
    (null, 'Assinaturas', '#6366F1', 'repeat'),
    (null, 'Educação', '#14B8A6', 'book'),
    (null, 'Transferência', '#6B7280', 'arrow-left-right'),
    (null, 'Outros', '#9CA3AF', 'circle-dashed');
