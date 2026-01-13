create table if not exists orgs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists members (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id) on delete cascade,
  user_id text not null,
  role text not null check (role in ('admin', 'agent', 'viewer')),
  created_at timestamptz not null default now(),
  unique (org_id, user_id)
);

insert into orgs (name, slug)
values ('Default', 'default')
on conflict (slug) do nothing;
