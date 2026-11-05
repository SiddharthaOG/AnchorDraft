-- Seed Script: Demo users, memberships, profiles, brand kit, rules, and approved facts
-- Usage: docker exec <container> psql -U postgres -d postgres \
--   -v owner_uid='<UUID>' -v creator1_uid='<UUID>' -v creator2_uid='<UUID>' -v reviewer_uid='<UUID>' \
--   -f /path/to/seed_users.sql
--
-- Prerequisites:
-- 1. Run migrations: supabase db reset
-- 2. Create four demo users in Supabase Auth (via Studio or Admin API)
-- 3. Get their UUIDs: SELECT id, email FROM auth.users WHERE email LIKE '%@axial.demo';
-- 4. Run this script with those UUIDs as psql variables.
--
-- This script uses insert-if-absent followed by verification. It does not silently
-- overwrite existing membership roles, brand kit status, rules, or approved facts.
-- If a seeded entity exists with different values, it raises an exception.

\set ON_ERROR_STOP on

-- ============================================================
-- Verify required UUID variables are provided
-- ============================================================
\if :{?owner_uid}
\else
    \echo 'ERROR: owner_uid variable not set.'
    \quit
\endif
\if :{?creator1_uid}
\else
    \echo 'ERROR: creator1_uid variable not set.'
    \quit
\endif
\if :{?creator2_uid}
\else
    \echo 'ERROR: creator2_uid variable not set.'
    \quit
\endif
\if :{?reviewer_uid}
\else
    \echo 'ERROR: reviewer_uid variable not set.'
    \quit
\endif

-- ============================================================
-- Create temporary function to do the seeding
-- ============================================================
CREATE OR REPLACE FUNCTION seed_demo_data(
    p_owner_uid uuid,
    p_creator1_uid uuid,
    p_creator2_uid uuid,
    p_reviewer_uid uuid
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    missing text := '';
    v_existing jsonb;
BEGIN
    -- Verify all four users exist in auth.users
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_owner_uid) THEN
        missing := missing || ' owner';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_creator1_uid) THEN
        missing := missing || ' creator1';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_creator2_uid) THEN
        missing := missing || ' creator2';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_reviewer_uid) THEN
        missing := missing || ' reviewer';
    END IF;
    IF missing <> '' THEN
        RAISE EXCEPTION 'Users not found in auth.users:%', missing;
    END IF;
    RAISE NOTICE 'All four demo users verified in auth.users';

    -- Verify organization exists
    IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = '11111111-1111-1111-1111-111111111111') THEN
        RAISE EXCEPTION 'Organization not found. Run migrations first.';
    END IF;
    RAISE NOTICE 'Organization verified';

    -- Insert profiles (insert-if-absent, verify on conflict)
    RAISE NOTICE 'Creating profiles...';
    INSERT INTO public.profiles (user_id, display_name, created_at)
    VALUES
        (p_owner_uid, 'Owner Manager', '2026-11-01 10:00:00+00'),
        (p_creator1_uid, 'Creator One', '2026-11-01 10:00:00+00'),
        (p_creator2_uid, 'Creator Two', '2026-11-01 10:00:00+00'),
        (p_reviewer_uid, 'Reviewer', '2026-11-01 10:00:00+00')
    ON CONFLICT (user_id) DO NOTHING;

    -- Verify profiles match expected
    IF EXISTS (
        SELECT 1 FROM public.profiles
        WHERE user_id = p_owner_uid AND display_name <> 'Owner Manager'
    ) THEN
        RAISE EXCEPTION 'Profile mismatch for owner_uid: display_name differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.profiles
        WHERE user_id = p_creator1_uid AND display_name <> 'Creator One'
    ) THEN
        RAISE EXCEPTION 'Profile mismatch for creator1_uid: display_name differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.profiles
        WHERE user_id = p_creator2_uid AND display_name <> 'Creator Two'
    ) THEN
        RAISE EXCEPTION 'Profile mismatch for creator2_uid: display_name differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.profiles
        WHERE user_id = p_reviewer_uid AND display_name <> 'Reviewer'
    ) THEN
        RAISE EXCEPTION 'Profile mismatch for reviewer_uid: display_name differs';
    END IF;

    -- Insert memberships (insert-if-absent, verify roles on conflict)
    RAISE NOTICE 'Creating memberships...';
    INSERT INTO public.memberships (org_id, user_id, roles, created_at)
    VALUES
        ('11111111-1111-1111-1111-111111111111', p_owner_uid, '{owner,manager}', '2026-11-01 10:00:00+00'),
        ('11111111-1111-1111-1111-111111111111', p_creator1_uid, '{creator}', '2026-11-01 10:00:00+00'),
        ('11111111-1111-1111-1111-111111111111', p_creator2_uid, '{creator}', '2026-11-01 10:00:00+00'),
        ('11111111-1111-1111-1111-111111111111', p_reviewer_uid, '{reviewer}', '2026-11-01 10:00:00+00')
    ON CONFLICT (org_id, user_id) DO NOTHING;

    -- Verify memberships match expected roles
    IF EXISTS (
        SELECT 1 FROM public.memberships
        WHERE org_id = '11111111-1111-1111-1111-111111111111' AND user_id = p_owner_uid
          AND roles <> '{owner,manager}'
    ) THEN
        RAISE EXCEPTION 'Membership mismatch for owner_uid: roles differ';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.memberships
        WHERE org_id = '11111111-1111-1111-1111-111111111111' AND user_id = p_creator1_uid
          AND roles <> '{creator}'
    ) THEN
        RAISE EXCEPTION 'Membership mismatch for creator1_uid: roles differ';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.memberships
        WHERE org_id = '11111111-1111-1111-1111-111111111111' AND user_id = p_creator2_uid
          AND roles <> '{creator}'
    ) THEN
        RAISE EXCEPTION 'Membership mismatch for creator2_uid: roles differ';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.memberships
        WHERE org_id = '11111111-1111-1111-1111-111111111111' AND user_id = p_reviewer_uid
          AND roles <> '{reviewer}'
    ) THEN
        RAISE EXCEPTION 'Membership mismatch for reviewer_uid: roles differ';
    END IF;

    -- Insert brand kit v1 (Active) using actual owner UUID
    RAISE NOTICE 'Creating brand kit v1...';
    INSERT INTO public.brand_kits (id, org_id, version, name, status, source_kit_id, created_by, created_at, activated_at)
    VALUES (
        '22222222-2222-2222-2222-222222222222',
        '11111111-1111-1111-1111-111111111111',
        1,
        'Axial Brand Guidelines v1',
        'active',
        NULL,
        p_owner_uid,
        '2026-11-01 10:00:00+00',
        '2026-11-01 10:00:00+00'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Verify brand kit matches expected values
    IF EXISTS (
        SELECT 1 FROM public.brand_kits
        WHERE id = '22222222-2222-2222-2222-222222222222'
          AND (status <> 'active' OR created_by <> p_owner_uid OR version <> 1 OR name <> 'Axial Brand Guidelines v1')
    ) THEN
        RAISE EXCEPTION 'Brand kit mismatch: status, created_by, version, or name differs';
    END IF;

    -- Insert 15 rules (insert-if-absent, verify on conflict)
    RAISE NOTICE 'Creating rules...';
    INSERT INTO public.rules (id, kit_id, rule_key, category, title, guideline_text, severity, check_kind, config, needs_reviewer, example_bad, example_good)
    VALUES
    -- TERMINOLOGY rules (deterministic term_map)
    (
        '30000001-0000-0000-0000-000000000001',
        '22222222-2222-2222-2222-222222222222',
        'TERM-01', 'terminology',
        'Prefer "use" over "utilize"',
        'Use simple, direct language. Replace "utilize" with "use".',
        'low', 'deterministic',
        '{"entries":[{"avoid":["utilize","utilizes","utilized"],"prefer":"use"}]}'::jsonb,
        false, 'We utilize the latest technology.', 'We use the latest technology.'
    ),
    (
        '30000001-0000-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222',
        'TERM-02', 'terminology',
        'Prefer "use" over "leverage"',
        'Avoid corporate jargon. Replace "leverage" with "use" or "apply".',
        'low', 'deterministic',
        '{"entries":[{"avoid":["leverage","leverages","leveraged"],"prefer":"use"}]}'::jsonb,
        false, 'We leverage our platform.', 'We use our platform.'
    ),
    (
        '30000001-0000-0000-0000-000000000003',
        '22222222-2222-2222-2222-222222222222',
        'TERM-03', 'terminology',
        'Prefer "help" over "facilitate"',
        'Use plain language. Replace "facilitate" with "help" or "enable".',
        'low', 'deterministic',
        '{"entries":[{"avoid":["facilitate","facilitates","facilitated"],"prefer":"help"}]}'::jsonb,
        false, 'This tool facilitates the process.', 'This tool helps the process.'
    ),
    (
        '30000001-0000-0000-0000-000000000004',
        '22222222-2222-2222-2222-222222222222',
        'TERM-04', 'terminology',
        'Avoid "synergy" and "synergistic"',
        'These are empty corporate buzzwords. Be specific about the benefit.',
        'low', 'deterministic',
        '{"phrases":["synergy","synergistic"]}'::jsonb,
        false, 'The partnership creates synergy.', 'The partnership reduces costs by 20%.'
    ),
    (
        '30000001-0000-0000-0000-000000000005',
        '22222222-2222-2222-2222-222222222222',
        'TERM-05', 'terminology',
        'Banned term: "disrupt"',
        'Do not use "disrupt" or "disruptive" unless describing a specific market event.',
        'medium', 'deterministic',
        '{"phrases":["disrupt","disruptive","disruption"]}'::jsonb,
        false, 'Our disruptive solution changes everything.', 'Our solution reduces deployment time by 50%.'
    ),

    -- CLAIM rules (LLM-checked, need reviewer)
    (
        '30000001-0000-0000-0000-000000000006',
        '22222222-2222-2222-2222-222222222222',
        'CLAIM-01', 'claim',
        'No absolute claims without evidence',
        'Do not use absolute terms like "guaranteed", "100%", "always", "never", "best", "#1" without approved facts to back them.',
        'high', 'llm', null,
        true, 'Our product is guaranteed to work 100% of the time.', 'Our product has a 99.9% uptime SLA (see FACT-01).'
    ),
    (
        '30000001-0000-0000-0000-000000000007',
        '22222222-2222-2222-2222-222222222222',
        'CLAIM-02', 'claim',
        'No "best in class" without proof',
        'Claims of superiority require approved benchmark data.',
        'high', 'llm', null,
        true, 'We are the best in class.', 'Our latency is 40% lower than the industry average (see FACT-02).'
    ),
    (
        '30000001-0000-0000-0000-000000000008',
        '22222222-2222-2222-2222-222222222222',
        'CLAIM-03', 'claim',
        'No unsupported factual claims',
        'Any factual or performance claim must be supported by an approved fact in the brand kit.',
        'high', 'llm', null,
        true, 'Our API processes 1M requests per second.', 'Our API processes up to 500K requests per second (see FACT-03).'
    ),

    -- TONE rules (LLM-checked)
    (
        '30000001-0000-0000-0000-000000000009',
        '22222222-2222-2222-2222-222222222222',
        'TONE-01', 'tone',
        'Professional but approachable',
        'Write in a professional yet conversational tone. Avoid overly formal language.',
        'medium', 'llm', null,
        false, 'It is imperative that users ascertain the functionality.', 'Users can easily check how it works.'
    ),
    (
        '30000001-0000-0000-0000-000000000010',
        '22222222-2222-2222-2222-222222222222',
        'TONE-02', 'tone',
        'Active voice preferred',
        'Use active voice. Passive voice obscures responsibility.',
        'medium', 'llm', null,
        false, 'Mistakes were made.', 'We made a mistake.'
    ),

    -- MESSAGING rules (LLM-checked)
    (
        '30000001-0000-0000-0000-000000000011',
        '22222222-2222-2222-2222-222222222222',
        'MSG-01', 'messaging',
        'Lead with customer benefit',
        'Start with what the customer gains, not what the product does.',
        'medium', 'llm', null,
        false, 'Our platform has a new dashboard.', 'Get real-time insights with our new dashboard.'
    ),
    (
        '30000001-0000-0000-0000-000000000012',
        '22222222-2222-2222-2222-222222222222',
        'MSG-02', 'messaging',
        'No jargon without explanation',
        'Technical terms must be explained on first use.',
        'low', 'llm', null,
        false, 'Our Kubernetes-native architecture...', 'Our Kubernetes-native architecture (built for container orchestration)...'
    ),

    -- ACCESSIBILITY rules (deterministic)
    (
        '30000001-0000-0000-0000-000000000013',
        '22222222-2222-2222-2222-222222222222',
        'A11Y-01', 'accessibility',
        'Images must have meaningful alt text',
        'All Markdown images must have descriptive alt text (minimum 5 characters, not generic like "image", "photo", "picture").',
        'high', 'deterministic',
        '{"min_length":5,"generic":["image","photo","picture","screenshot","diagram"]}'::jsonb,
        false, '![image](chart.png)', '![Quarterly revenue chart showing 20% growth](chart.png)'
    ),
    (
        '30000001-0000-0000-0000-000000000014',
        '22222222-2222-2222-2222-222222222222',
        'A11Y-02', 'accessibility',
        'No color-only information',
        'Do not rely on color alone to convey meaning. Use labels, patterns, or text.',
        'high', 'llm', null,
        false, 'The red line shows errors.', 'The red line (errors) shows failures.'
    ),
    (
        '30000001-0000-0000-0000-000000000015',
        '22222222-2222-2222-2222-222222222222',
        'A11Y-03', 'accessibility',
        'Descriptive link text',
        'Link text must describe the destination. Avoid "click here", "read more", "link".',
        'medium', 'llm', null,
        false, 'Click here for details.', 'View the full pricing details.'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Verify rules match expected values
    IF EXISTS (
        SELECT 1 FROM public.rules
        WHERE id = '30000001-0000-0000-0000-000000000001'
          AND (rule_key <> 'TERM-01' OR category <> 'terminology' OR severity <> 'low' OR check_kind <> 'deterministic')
    ) THEN
        RAISE EXCEPTION 'Rule TERM-01 mismatch: rule_key, category, severity, or check_kind differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.rules
        WHERE id = '30000001-0000-0000-0000-000000000006'
          AND (rule_key <> 'CLAIM-01' OR category <> 'claim' OR severity <> 'high' OR check_kind <> 'llm' OR needs_reviewer <> true)
    ) THEN
        RAISE EXCEPTION 'Rule CLAIM-01 mismatch: rule_key, category, severity, check_kind, or needs_reviewer differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.rules
        WHERE id = '30000001-0000-0000-0000-000000000013'
          AND (rule_key <> 'A11Y-01' OR category <> 'accessibility' OR severity <> 'high' OR check_kind <> 'deterministic')
    ) THEN
        RAISE EXCEPTION 'Rule A11Y-01 mismatch: rule_key, category, severity, or check_kind differs';
    END IF;

    -- Insert 5 approved facts (insert-if-absent, verify on conflict)
    RAISE NOTICE 'Creating approved facts...';
    INSERT INTO public.approved_facts (id, kit_id, fact_key, statement, source_note, valid_until)
    VALUES
    (
        '40000001-0000-0000-0000-000000000001',
        '22222222-2222-2222-2222-222222222222',
        'FACT-01',
        'Axial Platform maintains 99.9% uptime SLA.',
        'SLA Document v3.2, Section 4.1, dated 2026-01-15',
        '2027-01-15'
    ),
    (
        '40000001-0000-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222',
        'FACT-02',
        'Axial Platform API latency averages 45ms (p50) and 120ms (p99) in us-east-1.',
        'Internal Benchmark Report Q3 2026, dated 2026-09-01',
        '2027-09-01'
    ),
    (
        '40000001-0000-0000-0000-000000000003',
        '22222222-2222-2222-2222-222222222222',
        'FACT-03',
        'Axial Platform processes up to 500,000 requests per second per cluster.',
        'Load Test Results, Cluster Config v2.1, dated 2026-08-20',
        '2027-08-20'
    ),
    (
        '40000001-0000-0000-0000-000000000004',
        '22222222-2222-2222-2222-222222222222',
        'FACT-04',
        'Axial Platform is SOC 2 Type II certified.',
        'Audit Report by CyberShield Assessors, dated 2026-06-10',
        '2027-06-10'
    ),
    (
        '40000001-0000-0000-0000-000000000005',
        '22222222-2222-2222-2222-222222222222',
        'FACT-05',
        'Axial Platform supports GDPR data subject requests within 72 hours.',
        'Privacy Policy v4.0, Section 8, dated 2026-03-01',
        '2027-03-01'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Verify approved facts match expected values
    IF EXISTS (
        SELECT 1 FROM public.approved_facts
        WHERE id = '40000001-0000-0000-0000-000000000001'
          AND (fact_key <> 'FACT-01' OR statement <> 'Axial Platform maintains 99.9% uptime SLA.')
    ) THEN
        RAISE EXCEPTION 'Approved fact FACT-01 mismatch: fact_key or statement differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.approved_facts
        WHERE id = '40000001-0000-0000-0000-000000000003'
          AND (fact_key <> 'FACT-03' OR statement <> 'Axial Platform processes up to 500,000 requests per second per cluster.')
    ) THEN
        RAISE EXCEPTION 'Approved fact FACT-03 mismatch: fact_key or statement differs';
    END IF;

    RAISE NOTICE 'seed_users.sql completed successfully.';
END $$;

-- ============================================================
-- Execute the seeding function with psql variables
-- ============================================================
\echo 'Executing seed function...'
SELECT seed_demo_data(
    :'owner_uid',
    :'creator1_uid',
    :'creator2_uid',
    :'reviewer_uid'
);

-- ============================================================
-- Clean up
-- ============================================================
DROP FUNCTION seed_demo_data(uuid, uuid, uuid, uuid);

\echo 'seed_users.sql completed successfully.'