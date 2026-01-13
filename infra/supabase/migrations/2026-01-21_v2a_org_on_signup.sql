create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  org_name text;
  base_slug text;
  final_slug text;
  new_org_id uuid;
begin
  org_name :=
    coalesce(new.raw_user_meta_data->>'org_name', split_part(new.email, '@', 1), 'Workspace');
  base_slug := lower(regexp_replace(org_name, '[^a-z0-9]+', '-', 'g'));
  base_slug := trim(both '-' from base_slug);
  if base_slug is null or base_slug = '' then
    base_slug := 'workspace';
  end if;
  final_slug := left(base_slug, 24) || '-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 6);

  insert into public.orgs (name, slug)
  values (org_name, final_slug)
  returning id into new_org_id;

  insert into public.members (org_id, user_id, role)
  values (new_org_id, new.id::text, 'admin')
  on conflict (org_id, user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();
