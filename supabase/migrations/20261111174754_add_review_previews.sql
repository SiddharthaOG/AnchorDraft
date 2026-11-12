-- Short-lived, single-use approval records for exact redacted provider payloads.
begin;

create table public.review_previews (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    revision_id uuid not null references public.revisions(id) on delete cascade,
    kit_id uuid not null references public.brand_kits(id) on delete cascade,
    policy_version integer not null check (policy_version > 0),
    policy_sha256 text not null check (policy_sha256 ~ '^[0-9a-f]{64}$'),
    revision_sha256 text not null check (revision_sha256 ~ '^[0-9a-f]{64}$'),
    kit_sha256 text not null check (kit_sha256 ~ '^[0-9a-f]{64}$'),
    payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
    -- Contains redacted prompts and metadata only. No source text or image bytes.
    payload jsonb not null,
    -- Fernet-encrypted reverse map; decryption key exists only in the engine environment.
    reverse_map_ciphertext text not null,
    redaction_summary jsonb not null default '{}'::jsonb,
    asset_manifest jsonb not null default '[]'::jsonb,
    confirmation_token_sha256 text not null check (confirmation_token_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz not null,
    consumed_at timestamptz null,
    confirmed_by uuid null references auth.users(id) on delete cascade,
    image_consent_at timestamptz null,
    review_id uuid null references public.reviews(id) on delete set null,
    created_at timestamptz not null default now(),
    constraint review_previews_expiry_future check (expires_at > created_at),
    constraint review_previews_consumption_consistent check (
        (consumed_at is null and confirmed_by is null and review_id is null)
        or (consumed_at is not null and confirmed_by is not null)
    )
);

create index idx_review_previews_user_expiry
    on public.review_previews (user_id, expires_at desc);
create index idx_review_previews_org_revision
    on public.review_previews (org_id, revision_id, created_at desc);
create unique index idx_review_previews_review_unique
    on public.review_previews (review_id) where review_id is not null;

alter table public.reviews
    add column preview_id uuid null references public.review_previews(id) on delete set null;
create unique index idx_reviews_preview_unique
    on public.reviews (preview_id) where preview_id is not null;

alter table public.review_previews enable row level security;
revoke all on public.review_previews from anon, authenticated;
grant all on public.review_previews to service_role;

commit;
