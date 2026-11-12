-- Distinguish an unchanged revision from malformed revision content.
CREATE OR REPLACE FUNCTION public.create_revision(
    _content_id uuid,
    _body text
)
RETURNS TABLE (revision_id uuid, version int)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    _uid uuid := (SELECT auth.uid());
    _org uuid;
    _status public.content_status;
    _new_version int;
    _new_revision_id uuid;
    _latest_body text;
BEGIN
    IF _uid IS NULL THEN
        RAISE EXCEPTION 'unauthenticated';
    END IF;

    SELECT org_id, status INTO _org, _status
    FROM public.contents
    WHERE id = _content_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'not_found';
    END IF;

    IF NOT private.has_role(_org, 'creator') THEN
        RAISE EXCEPTION 'forbidden';
    END IF;

    IF _status NOT IN ('draft', 'changes_requested') THEN
        RAISE EXCEPTION 'conflict:not_editable';
    END IF;

    IF _body IS NULL OR length(_body) < 1 OR length(_body) > 20000 THEN
        RAISE EXCEPTION 'validation:body';
    END IF;

    SELECT body INTO _latest_body
    FROM public.revisions
    WHERE content_id = _content_id
    ORDER BY public.revisions.version DESC
    LIMIT 1;

    IF _latest_body = _body THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'duplicate_revision',
            DETAIL = 'The submitted body is identical to the latest revision.';
    END IF;

    SELECT COALESCE(MAX(public.revisions.version), 0) + 1 INTO _new_version
    FROM public.revisions
    WHERE content_id = _content_id;

    INSERT INTO public.revisions (content_id, version, parent_revision_id, body, source, created_by)
    SELECT _content_id, _new_version, id, _body, 'manual', _uid
    FROM public.revisions
    WHERE content_id = _content_id
    ORDER BY public.revisions.version DESC
    LIMIT 1
    RETURNING id INTO _new_revision_id;

    IF _status = 'changes_requested' THEN
        UPDATE public.contents
        SET status = 'draft', updated_at = now()
        WHERE id = _content_id;
    END IF;

    INSERT INTO public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    VALUES (_org, _uid, 'revision.created', 'revision', _new_revision_id,
            jsonb_build_object('version', _new_version));

    RETURN QUERY SELECT _new_revision_id, _new_version;
END;
$$;

REVOKE ALL ON FUNCTION public.create_revision(uuid, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.create_revision(uuid, text) TO authenticated;
