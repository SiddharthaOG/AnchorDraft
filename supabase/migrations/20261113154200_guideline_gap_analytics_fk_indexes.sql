-- Cover the new foreign keys to prevent avoidable scans during FK checks.
-- org_id on guideline_suggestions is already the leading column of
-- guideline_suggestions_org_status_created.

create index if not exists guideline_suggestions_source_kit_id_idx
    on public.guideline_suggestions (source_kit_id);
create index if not exists guideline_suggestions_created_by_idx
    on public.guideline_suggestions (created_by);
create index if not exists guideline_suggestions_resolved_by_idx
    on public.guideline_suggestions (resolved_by);
create index if not exists guideline_suggestions_accepted_kit_id_idx
    on public.guideline_suggestions (accepted_kit_id);
create index if not exists guideline_suggestion_previews_org_id_idx
    on public.guideline_suggestion_previews (org_id);
create index if not exists guideline_suggestion_previews_user_id_idx
    on public.guideline_suggestion_previews (user_id);
create index if not exists guideline_suggestion_previews_source_kit_id_idx
    on public.guideline_suggestion_previews (source_kit_id);
