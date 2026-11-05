"""Kit lint API endpoints."""
from fastapi import APIRouter, Depends, Path, status, HTTPException
from uuid import UUID

from app.auth.dependencies import AuthUser, get_current_user_single_org, require_owner
from app.auth.supabase import get_supabase_client

router = APIRouter()


@router.post(
    "/kits/{kit_id}/lint",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Kit lint completed"},
        403: {"description": "Forbidden - not an owner"},
        404: {"description": "Kit not found"},
    },
)
async def lint_kit(
    kit_id: UUID = Path(..., description="Kit ID to lint"),
    user=Depends(require_owner),
) -> dict:
    """Lint a draft brand kit for issues before activation.

    Requires owner role in the kit's organization.
    """
    supabase = get_supabase_client()

    # Get kit
    kit = supabase.get_kit(str(kit_id))
    if not kit:
        raise HTTPException(status_code=404, detail="Kit not found")

    # Verify ownership - kit must belong to the user's organization
    if kit.get("org_id") != user.org_id:
        # Don't leak existence - return 404
        raise HTTPException(status_code=404, detail="Kit not found")

    # Get kit rules and facts
    rules = supabase.get_kit_rules(str(kit_id))
    facts = supabase.get_kit_facts(str(kit_id))

    issues = []
    warnings = []

    # Check: kit has at least one rule
    if not rules:
        issues.append({
            "severity": "error",
            "code": "EMPTY_KIT",
            "ref_key": None,
            "message": "Kit must have at least one rule",
        })

    # Check: rules have valid config
    for rule in rules:
        if rule["check_kind"] == "deterministic":
            config = rule.get("config") or {}
            if not config.get("entries") and not config.get("phrases"):
                issues.append({
                    "severity": "error",
                    "code": "INVALID_CONFIG",
                    "ref_key": rule.get("rule_key"),
                    "message": f"Deterministic rule {rule.get('rule_key')} has invalid config",
                })

        # Check: rule has guideline text
        if not rule.get("guideline_text"):
            issues.append({
                "severity": "error",
                "code": "EMPTY_GUIDELINE",
                "ref_key": rule.get("rule_key"),
                "message": f"Rule {rule.get('rule_key')} has empty guideline text",
            })

    # Check: facts not past valid_until
    from datetime import date
    today = date.today()
    for fact in facts:
        valid_until = fact.get("valid_until")
        if valid_until and valid_until < today.isoformat():
            warnings.append(f"Fact {fact.get('fact_key')} is past its valid_until date")

    # Calculate prompt size estimate
    total_chars = sum(
        len(r.get("guideline_text", "")) for r in rules
    ) + sum(
        len(f.get("statement", "")) + len(f.get("source_note", "")) for f in facts
    )
    prompt_cap = 24000  # From REVIEW_ENGINE.md

    if total_chars > prompt_cap:
        issues.append({
            "severity": "error",
            "code": "KIT_TOO_LARGE",
            "ref_key": None,
            "message": f"Kit exceeds prompt character cap ({total_chars} > {prompt_cap})",
        })

    # Count rule types
    llm_rules = sum(1 for r in rules if r.get("check_kind") == "llm")
    deterministic_rules = sum(1 for r in rules if r.get("check_kind") == "deterministic")

    ok = len(issues) == 0

    issues_output = [
        {
            "severity": i["severity"],
            "code": i["code"],
            "ref_key": i.get("ref_key"),
            "message": i["message"],
        }
        for i in issues
    ]

    stats = {
        "rules": len(rules),
        "facts": len(facts),
        "llm_rules": llm_rules,
        "deterministic_rules": deterministic_rules,
        "prompt_chars_estimate": total_chars,
        "prompt_chars_cap": 24000,
    }

    return {
        "ok": ok,
        "issues": issues_output,
        "stats": stats,
    }