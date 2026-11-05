-- Seed Script: Sample content with revisions (demo scenario with planted issues)
-- Usage: docker exec <container> psql -U postgres -d postgres \
--   -v creator1_uid='<UUID>' \
--   -f /path/to/seed_content.sql
--
-- Prerequisites:
-- 1. Run migrations: supabase db reset
-- 2. Create demo users in Supabase Auth (via Studio or Admin API)
-- 3. Run seed_users.sql with all four UUIDs
-- 4. Run this script with creator1_uid variable.
--
-- Revisions are append-only (immutable). This script uses ON CONFLICT DO NOTHING
-- for revisions and verifies that any existing revisions match the expected
-- seed content. A conflict with different content raises an exception.
-- All important fields are verified: content_id, version, parent_revision_id,
-- body, source, and created_by.

\set ON_ERROR_STOP on

-- ============================================================
-- Verify required UUID variable is provided
-- ============================================================
\if :{?creator1_uid}
\else
    \echo 'ERROR: creator1_uid variable not set.'
    \quit
\endif

-- ============================================================
-- Create temporary function to do the seeding
-- ============================================================
CREATE OR REPLACE FUNCTION seed_demo_content(p_creator1_uid uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_existing_body text;
    v_expected_body text;
BEGIN
    -- Verify creator1 user exists in auth.users
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_creator1_uid) THEN
        RAISE EXCEPTION 'User % not found in auth.users. Run seed_users.sql first.', p_creator1_uid;
    END IF;
    RAISE NOTICE 'Creator1 user verified';

    -- Verify organization exists
    IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = '11111111-1111-1111-1111-111111111111') THEN
        RAISE EXCEPTION 'Organization not found. Run migrations first.';
    END IF;

    -- ============================================================
    -- 5. Sample Content with Two Revisions (demo scenario)
    -- ============================================================
    -- Content: Draft blog post with planted issues (mutable - OK to upsert)
    RAISE NOTICE 'Creating sample content...';
    INSERT INTO public.contents (id, org_id, title, channel, purpose, status, created_by, created_at, updated_at)
    VALUES (
        '50000001-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'Announcing Axial Platform 2.0',
        'blog',
        'Announce the 2.0 release and drive signups from developers',
        'draft',
        p_creator1_uid,
        '2026-11-02 10:00:00+00',
        '2026-11-02 10:00:00+00'
    )
    ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        channel = EXCLUDED.channel,
        purpose = EXCLUDED.purpose,
        status = EXCLUDED.status,
        created_by = EXCLUDED.created_by,
        updated_at = EXCLUDED.updated_at;

    -- Revision 1: Contains 4 planted issues (append-only - DO NOTHING on conflict)
    -- 1. "utilize" (TERM-01)
    -- 2. "guaranteed 100% uptime" (CLAIM-01 - absolute claim)
    -- 3. "processes 1M requests per second" (CLAIM-03 - unsupported fact, contradicts FACT-03)
    -- 4. Missing alt text on image (A11Y-01)
    RAISE NOTICE 'Creating revision 1...';
    v_expected_body :=
    '# Announcing Axial Platform 2.0

We are excited to announce Axial Platform 2.0, the next generation of our developer platform.

## What''s New

Our team has worked tirelessly to **utilize** the latest cloud-native technologies to deliver a platform that is **guaranteed to provide 100% uptime**. With our new architecture, the platform **processes 1M requests per second**, making it the fastest in the industry.

![image](architecture-diagram.png)

## Key Benefits

- **Seamless scaling**: Automatically scales from 0 to millions of requests.
- **Enterprise security**: SOC 2 Type II certified with GDPR compliance.
- **Developer experience**: New CLI, improved docs, and faster builds.

## Get Started

[Click here](https://axial.demo/signup) to sign up for early access.

We can''t wait to see what you build!';

    INSERT INTO public.revisions (id, content_id, version, parent_revision_id, body, source, created_by, created_at)
    VALUES (
        '60000001-0000-0000-0000-000000000001',
        '50000001-0000-0000-0000-000000000001',
        1,
        NULL,
        v_expected_body,
        'manual',
        p_creator1_uid,
        '2026-11-02 10:00:00+00'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Verify revision 1 matches expected content (all important fields)
    SELECT body, content_id, version, parent_revision_id, source, created_by
    INTO v_existing_body, v_expected_body, v_expected_body, v_expected_body, v_expected_body, v_expected_body
    FROM public.revisions WHERE id = '60000001-0000-0000-0000-000000000001';

    -- Verify all important fields
    IF EXISTS (
        SELECT 1 FROM public.revisions
        WHERE id = '60000001-0000-0000-0000-000000000001'
          AND (content_id <> '50000001-0000-0000-0000-000000000001'
               OR version <> 1
               OR parent_revision_id IS NOT NULL
               OR body IS DISTINCT FROM
    '# Announcing Axial Platform 2.0

We are excited to announce Axial Platform 2.0, the next generation of our developer platform.

## What''s New

Our team has worked tirelessly to **utilize** the latest cloud-native technologies to deliver a platform that is **guaranteed to provide 100% uptime**. With our new architecture, the platform **processes 1M requests per second**, making it the fastest in the industry.

![image](architecture-diagram.png)

## Key Benefits

- **Seamless scaling**: Automatically scales from 0 to millions of requests.
- **Enterprise security**: SOC 2 Type II certified with GDPR compliance.
- **Developer experience**: New CLI, improved docs, and faster builds.

## Get Started

[Click here](https://axial.demo/signup) to sign up for early access.

We can''t wait to see what you build!'
               OR source <> 'manual'
               OR created_by <> p_creator1_uid)
    ) THEN
        RAISE EXCEPTION 'Revision 1 mismatch: content_id, version, parent_revision_id, body, source, or created_by differs';
    END IF;

    -- Revision 2: After applying some decisions (append-only - DO NOTHING on conflict)
    -- Accepted TERM-01 (utilize -> use), dismissed CLAIM-01 with reason, kept others
    RAISE NOTICE 'Creating revision 2...';
    v_expected_body :=
    '# Announcing Axial Platform 2.0

We are excited to announce Axial Platform 2.0, the next generation of our developer platform.

## What''s New

Our team has worked tirelessly to **use** the latest cloud-native technologies to deliver a platform that is **guaranteed to provide 100% uptime**. With our new architecture, the platform **processes 1M requests per second**, making it the fastest in the industry.

![Architecture diagram showing microservices](architecture-diagram.png)

## Key Benefits

- **Seamless scaling**: Automatically scales from 0 to millions of requests.
- **Enterprise security**: SOC 2 Type II certified with GDPR compliance.
- **Developer experience**: New CLI, improved docs, and faster builds.

## Get Started

[View the full pricing details](https://axial.demo/signup) to sign up for early access.

We can''t wait to see what you build!';

    INSERT INTO public.revisions (id, content_id, version, parent_revision_id, body, source, created_by, created_at)
    VALUES (
        '60000001-0000-0000-0000-000000000002',
        '50000001-0000-0000-0000-000000000001',
        2,
        '60000001-0000-0000-0000-000000000001',
        v_expected_body,
        'accepted_suggestion',
        p_creator1_uid,
        '2026-11-02 14:00:00+00'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Verify revision 2 matches expected content (all important fields)
    IF EXISTS (
        SELECT 1 FROM public.revisions
        WHERE id = '60000001-0000-0000-0000-000000000002'
          AND (content_id <> '50000001-0000-0000-0000-000000000001'
               OR version <> 2
               OR parent_revision_id <> '60000001-0000-0000-0000-000000000001'
               OR body IS DISTINCT FROM
    '# Announcing Axial Platform 2.0

We are excited to announce Axial Platform 2.0, the next generation of our developer platform.

## What''s New

Our team has worked tirelessly to **use** the latest cloud-native technologies to deliver a platform that is **guaranteed to provide 100% uptime**. With our new architecture, the platform **processes 1M requests per second**, making it the fastest in the industry.

![Architecture diagram showing microservices](architecture-diagram.png)

## Key Benefits

- **Seamless scaling**: Automatically scales from 0 to millions of requests.
- **Enterprise security**: SOC 2 Type II certified with GDPR compliance.
- **Developer experience**: New CLI, improved docs, and faster builds.

## Get Started

[View the full pricing details](https://axial.demo/signup) to sign up for early access.

We can''t wait to see what you build!'
               OR source <> 'accepted_suggestion'
               OR created_by <> p_creator1_uid)
    ) THEN
        RAISE EXCEPTION 'Revision 2 mismatch: content_id, version, parent_revision_id, body, source, or created_by differs';
    END IF;

    RAISE NOTICE 'seed_content.sql completed successfully.';
END $$;

-- ============================================================
-- Execute the seeding function with psql variable
-- ============================================================
\echo 'Executing seed_content function...'
SELECT seed_demo_content(:'creator1_uid');

-- ============================================================
-- Clean up
-- ============================================================
DROP FUNCTION seed_demo_content(uuid);

\echo 'seed_content.sql completed successfully.'