"""Supabase service-role client for server-side operations."""
from supabase import create_client, Client
from app.core.config import get_settings


class SupabaseClient:
    """Supabase service-role client for server-side operations."""

    def __init__(self):
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create the Supabase service-role client."""
        if self._client is None:
            settings = get_settings()
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        return self._client

    def get_user_memberships(self, user_id: str) -> list[dict]:
        """Get all memberships for a user."""
        client = self._get_client()
        response = client.table("memberships").select("org_id, roles").eq("user_id", user_id).execute()
        return response.data or []

    def get_organization(self, org_id: str) -> dict | None:
        """Get organization by ID."""
        client = self._get_client()
        response = client.table("organizations").select("*").eq("id", org_id).execute()
        return response.data[0] if response.data else None

    def get_kit(self, kit_id: str) -> dict | None:
        """Get a kit by ID."""
        client = self._get_client()
        response = client.table("brand_kits").select("*").eq("id", kit_id).execute()
        return response.data[0] if response.data else None

    def get_active_kit(self, org_id: str) -> dict | None:
        """Get the active brand kit for an organization."""
        client = self._get_client()
        response = (
            client.table("brand_kits")
            .select("*")
            .eq("org_id", org_id)
            .eq("status", "active")
            .execute()
        )
        return response.data[0] if response.data else None

    def get_kit_rules(self, kit_id: str) -> list[dict]:
        """Get all rules for a kit."""
        client = self._get_client()
        response = client.table("rules").select("*").eq("kit_id", kit_id).execute()
        return response.data or []

    def get_kit_facts(self, kit_id: str) -> list[dict]:
        """Get all approved facts for a kit."""
        client = self._get_client()
        response = client.table("approved_facts").select("*").eq("kit_id", kit_id).execute()
        return response.data or []

    def get_revision(self, revision_id: str) -> dict | None:
        """Get a revision by ID."""
        client = self._get_client()
        response = client.table("revisions").select("*").eq("id", revision_id).execute()
        return response.data[0] if response.data else None

    def get_content(self, content_id: str) -> dict | None:
        """Get content by ID."""
        client = self._get_client()
        response = client.table("contents").select("*").eq("id", content_id).execute()
        return response.data[0] if response.data else None

    def get_visual_asset(self, asset_id: str) -> dict | None:
        """Get a visual asset by ID."""
        client = self._get_client()
        response = client.table("visual_assets").select("*").eq("id", asset_id).execute()
        return response.data[0] if response.data else None

    def create_review(
        self,
        org_id: str,
        revision_id: str,
        kit_id: str,
        requested_by: str,
        engine_version: str,
    ) -> dict:
        """Create a new review row."""
        client = self._get_client()
        response = (
            client.table("reviews")
            .insert(
                {
                    "org_id": org_id,
                    "revision_id": revision_id,
                    "kit_id": kit_id,
                    "engine_version": engine_version,
                    "requested_by": requested_by,
                }
            )
            .execute()
        )
        if not response.data:
            raise RuntimeError("Supabase write succeeded but returned no row")
        return response.data[0]

    def get_latest_review_for_revision(self, revision_id: str) -> dict | None:
        """Get the latest review for a revision."""
        client = self._get_client()
        response = (
            client.table("reviews")
            .select("*")
            .eq("revision_id", revision_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_existing_queued_or_running_review(self, revision_id: str) -> dict | None:
        """Get an existing queued or running review for deduplication."""
        client = self._get_client()
        response = (
            client.table("reviews")
            .select("*")
            .eq("revision_id", revision_id)
            .in_("status", ["queued", "running"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_latest_completed_review(self, revision_id: str) -> dict | None:
        """Get the latest completed review with ok/skipped llm_status for deduplication."""
        client = self._get_client()
        response = (
            client.table("reviews")
            .select("*")
            .eq("revision_id", revision_id)
            .eq("status", "done")
            .in_("llm_status", ["ok", "skipped"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def update_review_status(
        self,
        review_id: str,
        status: str,
        llm_status: str | None = None,
        warnings: list | None = None,
        llm_findings_raw: int | None = None,
        llm_findings_dropped: int | None = None,
        validator_stats: dict | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> dict:
        """Update a review row."""
        client = self._get_client()
        update_data = {"status": status}
        if llm_status is not None:
            update_data["llm_status"] = llm_status
        if warnings is not None:
            update_data["warnings"] = warnings
        if llm_findings_raw is not None:
            update_data["llm_findings_raw"] = llm_findings_raw
        if llm_findings_dropped is not None:
            update_data["llm_findings_dropped"] = llm_findings_dropped
        if validator_stats is not None:
            update_data["validator_stats"] = validator_stats
        if model is not None:
            update_data["model"] = model
        if prompt_version is not None:
            update_data["prompt_version"] = prompt_version

        response = (
            client.table("reviews").update(update_data).eq("id", review_id).execute()
        )
        if not response.data:
            raise RuntimeError("Supabase write succeeded but returned no row")
        return response.data[0]

    def link_visual_asset_to_content(
        self,
        visual_asset_id: str,
        content_id: str,
        revision_id: str,
        actor_user_id: str,
    ) -> None:
        """Link a visual asset to content/revision with explicit actor identity.

        Uses the service-role client but passes the authenticated user's ID
        to the RPC for proper authorization checks.
        """
        client = self._get_client()
        try:
            client.rpc("link_visual_asset_to_content", {
                "_visual_asset_id": visual_asset_id,
                "_content_id": content_id,
                "_revision_id": revision_id,
                "_actor_user_id": actor_user_id,
            }).execute()
        except Exception as e:
            raise RuntimeError(f"Failed to link visual asset to content: {e}")


# Global client instance
_supabase_client: "SupabaseClient | None" = None


def get_supabase_client() -> SupabaseClient:
    """Get the global Supabase service-role client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client