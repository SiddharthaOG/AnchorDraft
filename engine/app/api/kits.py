"""Kit lint API endpoints."""
import json
import re
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.auth.dependencies import AuthUser, get_current_user_single_org, require_owner
from app.auth.supabase import get_supabase_client
from app.store.db import DatabasePool, get_db_pool
from app.checks.deterministic import check_map
from app.checks.deterministic import RuleConfig

router = APIRouter()


def _resolve_deterministic_check_type(config: dict) -> str | None:
    """Resolve explicit or legacy deterministic check configuration.

    Older seeded kits omit the check discriminator. Infer only when exactly
    one supported check's required-key signature matches; ambiguous shapes
    fail closed rather than guessing.
    """
    declared = config.get("check")
    if declared is not None:
        return declared if isinstance(declared, str) and declared in check_map else None

    signatures = {
        "term_map": {"entries"},
        "phrase_list": {"phrases"},
        "missing_alt_text": {"min_length", "generic"},
        "required_disclosure": {"when_any", "require_any"},
    }
    matches = [
        name for name, required_keys in signatures.items()
        if required_keys.issubset(config.keys())
    ]
    return matches[0] if len(matches) == 1 else None


class _VisualGuidelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualLogoGuidelines(_VisualGuidelineModel):
    required: bool = False
    description: str | None = Field(default=None, max_length=500)
    variants: list[str] = Field(default_factory=list, max_length=8)
    clear_space_ratio: float = Field(default=0.1, ge=0, le=1)
    min_size_px: int = Field(default=32, ge=1, le=4096)

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 80 for value in normalized):
            raise ValueError("Logo variants must be non-empty and at most 80 characters")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("Logo variants must be unique")
        return normalized


class VisualPaletteColor(_VisualGuidelineModel):
    name: str = Field(min_length=1, max_length=40)
    hex: str = Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class VisualPaletteGuidelines(_VisualGuidelineModel):
    colors: list[VisualPaletteColor] = Field(min_length=1, max_length=12)
    tolerance: float = Field(default=10, ge=0, le=100)
    allow_neutrals: bool = True


class VisualContrastGuidelines(_VisualGuidelineModel):
    min_ratio: float = Field(default=4.5, ge=1, le=21)
    level: Literal["AA", "AAA"] = "AA"
    ignore_backgrounds: list[str] = Field(
        default_factory=lambda: ["#FFFFFF", "#000000"],
        max_length=8,
    )

    @field_validator("ignore_backgrounds")
    @classmethod
    def validate_backgrounds(cls, values: list[str]) -> list[str]:
        normalized = [value.upper() for value in values]
        if any(not re.fullmatch(r"#(?:[0-9A-F]{3}|[0-9A-F]{6})", value) for value in normalized):
            raise ValueError("Ignored backgrounds must be 3- or 6-digit hex colors")
        return normalized


class VisualGuidelines(_VisualGuidelineModel):
    logo: VisualLogoGuidelines | None = None
    palette: VisualPaletteGuidelines | None = None
    contrast: VisualContrastGuidelines | None = None


class UpdateVisualGuidelinesRequest(_VisualGuidelineModel):
    visual_guidelines: VisualGuidelines


class UpdateKitNameRequest(_VisualGuidelineModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Kit name cannot be empty")
        return normalized


@router.patch(
    "/kits/{kit_id}/name",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Kit name saved"},
        403: {"description": "Forbidden - not an owner"},
        404: {"description": "Kit not found"},
        409: {"description": "Only draft kits can be edited"},
        422: {"description": "Invalid kit name"},
    },
)
async def update_kit_name(
    kit_id: UUID = Path(..., description="Draft brand kit ID"),
    body: UpdateKitNameRequest = ...,
    user: AuthUser = Depends(require_owner),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Rename an owner-managed draft kit without changing its version or rules."""
    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            kit = await conn.fetchrow(
                """
                select id, status, name
                  from public.brand_kits
                 where id = $1 and org_id = $2
                 for update
                """,
                kit_id,
                user.org_id,
            )
            if not kit:
                raise HTTPException(status_code=404, detail="Kit not found")
            if kit["status"] != "draft":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": {
                            "code": "kit_not_editable",
                            "message": "Only draft kits can be renamed",
                        }
                    },
                )

            updated = await conn.fetchrow(
                """
                update public.brand_kits
                   set name = $3
                 where id = $1 and org_id = $2 and status = 'draft'
                returning name
                """,
                kit_id,
                user.org_id,
                body.name,
            )
            if not updated:
                raise HTTPException(status_code=409, detail="Kit changed while saving its name")

            await conn.execute(
                """
                insert into public.audit_log
                    (org_id, actor_id, action, entity_type, entity_id, detail)
                values ($1, $2, 'kit.renamed', 'brand_kit', $3, $4::jsonb)
                """,
                user.org_id,
                user.user_id,
                kit_id,
                json.dumps({"previous_name": kit["name"], "name": body.name}, separators=(",", ":")),
            )

    return {"kit_id": str(kit_id), "name": body.name}


@router.put(
    "/kits/{kit_id}/visual-guidelines",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Visual guidelines saved"},
        403: {"description": "Forbidden - not an owner"},
        404: {"description": "Kit not found"},
        409: {"description": "Only draft kits can be edited"},
        422: {"description": "Invalid visual guidelines"},
    },
)
async def update_visual_guidelines(
    kit_id: UUID = Path(..., description="Draft brand kit ID"),
    body: UpdateVisualGuidelinesRequest = ...,
    user: AuthUser = Depends(require_owner),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Save validated visual guidelines on an owner-managed draft kit."""
    guidelines = body.visual_guidelines.model_dump(exclude_none=True)
    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            kit = await conn.fetchrow(
                """
                select id, status
                  from public.brand_kits
                 where id = $1 and org_id = $2
                 for update
                """,
                kit_id,
                user.org_id,
            )
            if not kit:
                raise HTTPException(status_code=404, detail="Kit not found")
            if kit["status"] != "draft":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": {
                            "code": "kit_not_editable",
                            "message": "Visual guidelines can only be changed on draft kits",
                        }
                    },
                )

            updated = await conn.fetchrow(
                """
                update public.brand_kits
                   set visual_guidelines = $3::jsonb
                 where id = $1 and org_id = $2 and status = 'draft'
                returning visual_guidelines
                """,
                kit_id,
                user.org_id,
                json.dumps(guidelines, separators=(",", ":")),
            )
            if not updated:
                raise HTTPException(status_code=409, detail="Kit changed while saving visual guidelines")

            await conn.execute(
                """
                insert into public.audit_log
                    (org_id, actor_id, action, entity_type, entity_id, detail)
                values ($1, $2, 'kit.visual_guidelines_updated', 'brand_kit', $3, $4::jsonb)
                """,
                user.org_id,
                user.user_id,
                kit_id,
                json.dumps(
                    {
                        "logo_configured": "logo" in guidelines,
                        "palette_color_count": len(guidelines.get("palette", {}).get("colors", [])),
                        "contrast_configured": "contrast" in guidelines,
                    },
                    separators=(",", ":"),
                ),
            )

    return {
        "kit_id": str(kit_id),
        "visual_guidelines": guidelines,
    }



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
):
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

    try:
        VisualGuidelines.model_validate(kit.get("visual_guidelines") or {})
    except ValidationError:
        issues.append({
            "severity": "error",
            "code": "INVALID_VISUAL_GUIDELINES",
            "ref_key": None,
            "message": "Visual brand guidelines contain invalid configuration",
        })

    # Validate all rules first, building a consistently validated collection
    # of dictionary rules for all subsequent processing.
    validated_rules = []
    for rule in rules:
        if not isinstance(rule, dict):
            issues.append({
                "severity": "error",
                "code": "INVALID_RULE",
                "ref_key": None,
                "message": "Rule must be a dictionary",
            })
            continue

        rule_key = rule.get("rule_key")

        # Validate guideline_text for ALL rule types (LLM and deterministic)
        guideline_text = rule.get("guideline_text")
        if not isinstance(guideline_text, str) or not guideline_text.strip():
            issues.append({
                "severity": "error",
                "code": "EMPTY_GUIDELINE" if isinstance(guideline_text, str) and not guideline_text.strip() else "INVALID_GUIDELINE_TEXT",
                "ref_key": rule_key,
                "message": f"Rule {rule_key} guideline_text must be a non-empty string",
            })

        # Validate check_kind against supported values
        check_kind = rule.get("check_kind")
        if not isinstance(check_kind, str) or check_kind not in ("deterministic", "llm"):
            issues.append({
                "severity": "error",
                "code": "UNKNOWN_CHECK_KIND",
                "ref_key": rule_key,
                "message": f"Rule {rule_key} check_kind must be 'deterministic' or 'llm', got {check_kind!r}",
            })

        # Only validate deterministic config for deterministic rules
        if rule.get("check_kind") == "deterministic":
            raw_config = rule.get("config")

            if not isinstance(raw_config, dict):
                issues.append({
                    "severity": "error",
                    "code": "INVALID_CONFIG",
                    "ref_key": rule_key,
                    "message": "Deterministic rule config must be a dictionary",
                })
            else:
                check_type = _resolve_deterministic_check_type(raw_config)

                if check_type is None:
                    declared_check = raw_config.get("check")
                    issues.append({
                        "severity": "error",
                        "code": "UNKNOWN_CHECK_TYPE",
                        "ref_key": rule_key,
                        "message": f"Unknown or ambiguous deterministic check type: {declared_check!r}",
                    })
                else:
                    # Normalize legacy configurations in memory so downstream
                    # lint limits and validators use the same resolved type.
                    raw_config = {**raw_config, "check": check_type}
                    rule["config"] = raw_config
                    try:
                        checker = check_map[check_type](RuleConfig(
                            check=check_type,
                            config=raw_config,
                            rule_key=rule["rule_key"],
                            category=rule["category"],
                            severity=rule["severity"],
                            guideline_text=rule.get("guideline_text", ""),
                            needs_reviewer=rule.get("needs_reviewer", False),
                        ))
                        checker.validate_config()
                    except ValueError as e:
                        issues.append({
                            "severity": "error",
                            "code": "INVALID_CONFIG",
                            "ref_key": rule_key,
                            "message": (
                                f"Deterministic rule {rule.get('rule_key')} "
                                f"has invalid config: {e}"
                            ),
                        })
                    except Exception as e:
                        issues.append({
                            "severity": "error",
                            "code": "INVALID_CONFIG",
                            "ref_key": rule_key,
                            "message": (
                                f"Deterministic rule {rule.get('rule_key')} "
                                f"has invalid config: {type(e).__name__}"
                            ),
                        })

        # Add to validated collection for downstream use (only dict rules reach here)
        validated_rules.append(rule)

    # Check: kit has at least one valid (dictionary) rule
    if not validated_rules:
        issues.append({
            "severity": "error",
            "code": "EMPTY_KIT",
            "ref_key": None,
            "message": "Kit must have at least one valid rule",
        })

    # Validate facts
    validated_facts = []
    for fact in facts:
        if not isinstance(fact, dict):
            issues.append({
                "severity": "error",
                "code": "INVALID_FACT",
                "ref_key": None,
                "message": "Fact must be a dictionary",
            })
            continue

        fact_key = fact.get("fact_key")
        fact_has_errors = False

        # Validate statement (required, non-empty string, no whitespace-only)
        if "statement" not in fact:
            issues.append({
                "severity": "error",
                "code": "EMPTY_FACT_STATEMENT",
                "ref_key": fact_key,
                "message": f"Fact {fact_key} statement must be a non-empty string",
            })
            fact_has_errors = True
        else:
            statement = fact.get("statement")
            if not isinstance(statement, str) or not statement.strip():
                issues.append({
                    "severity": "error",
                    "code": "EMPTY_FACT_STATEMENT" if isinstance(statement, str) and not statement.strip() else "INVALID_FACT_STATEMENT",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} statement must be a non-empty string",
                })
                fact_has_errors = True

        # Validate source_note (required string, no whitespace-only)
        if "source_note" not in fact:
            issues.append({
                "severity": "error",
                "code": "EMPTY_FACT_SOURCE_NOTE",
                "ref_key": fact_key,
                "message": f"Fact {fact_key} source_note must be a non-empty string",
            })
            fact_has_errors = True
        else:
            source_note = fact.get("source_note")
            if not isinstance(source_note, str) or not source_note.strip():
                issues.append({
                    "severity": "error",
                    "code": "EMPTY_FACT_SOURCE_NOTE" if isinstance(source_note, str) and not source_note.strip() else "INVALID_FACT_SOURCE_NOTE",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} source_note must be a non-empty string",
                })
                fact_has_errors = True

        # Validate valid_until (optional, must be exact YYYY-MM-DD format if present)
        valid_until = fact.get("valid_until")
        if valid_until is not None:
            if not isinstance(valid_until, str):
                issues.append({
                    "severity": "error",
                    "code": "INVALID_FACT_VALID_UNTIL",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} valid_until must be a string in YYYY-MM-DD format",
                })
                fact_has_errors = True
            elif not valid_until.strip():
                issues.append({
                    "severity": "error",
                    "code": "INVALID_FACT_VALID_UNTIL",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} valid_until must be a non-empty string in YYYY-MM-DD format",
                })
                fact_has_errors = True
            elif not valid_until.strip() == valid_until:
                issues.append({
                    "severity": "error",
                    "code": "INVALID_FACT_VALID_UNTIL",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} valid_until must not have leading/trailing whitespace",
                })
                fact_has_errors = True
            elif len(valid_until) != 10 or not valid_until[:4].isdigit() or valid_until[4] != '-' or not valid_until[5:7].isdigit() or valid_until[7] != '-' or not valid_until[8:].isdigit():
                issues.append({
                    "severity": "error",
                    "code": "INVALID_FACT_VALID_UNTIL",
                    "ref_key": fact_key,
                    "message": f"Fact {fact_key} valid_until must be in YYYY-MM-DD format",
                })
                fact_has_errors = True
            else:
                try:
                    date.fromisoformat(valid_until)
                except ValueError:
                    issues.append({
                        "severity": "error",
                        "code": "INVALID_FACT_VALID_UNTIL",
                        "ref_key": fact_key,
                        "message": f"Fact {fact_key} valid_until must be a valid calendar date in YYYY-MM-DD format",
                    })
                    fact_has_errors = True

        # Add valid fact to validated collection only if no errors
        if not fact_has_errors:
            validated_facts.append(fact)

    # Check: facts not past valid_until (only for valid facts with valid_until)
    today = date.today()
    for fact in validated_facts:
        if not isinstance(fact, dict):
            continue
        valid_until = fact.get("valid_until")
        if valid_until:
            try:
                valid_date = date.fromisoformat(valid_until)
                if valid_date < today:
                    warnings.append(f"Fact {fact.get('fact_key')} is past its valid_until date")
            except ValueError:
                # Invalid date format already caught above
                pass

    # Enforce documented limits (from REVIEW_ENGINE.md)
    # Limit: at most 100 phrases per rule, each at most 100 characters
    # Limit: at most 50 deterministic rules per kit
    # Use validated_rules for consistent, safe processing
    deterministic_rules_list = [r for r in validated_rules if r.get("check_kind") == "deterministic"]
    if len(deterministic_rules_list) > 50:
        issues.append({
            "severity": "error",
            "code": "TOO_MANY_DETERMINISTIC_RULES",
            "ref_key": None,
            "message": f"Kit exceeds maximum of 50 deterministic rules (has {len(deterministic_rules_list)})",
        })

    for rule in deterministic_rules_list:
        config = rule.get("config")
        if not isinstance(config, dict):
            continue

        check_type = config.get("check")
        if not isinstance(check_type, str):
            continue
        if check_type == "term_map":
            entries = config.get("entries")
            if isinstance(entries, list):
                if len(entries) > 100:
                    issues.append({
                        "severity": "error",
                        "code": "TOO_MANY_TERM_MAP_ENTRIES",
                        "ref_key": rule.get("rule_key"),
                        "message": f"Term map rule {rule.get('rule_key')} exceeds 100 entries (has {len(entries)})",
                    })
                for entry in entries:
                    if isinstance(entry, dict):
                        avoid_terms = entry.get("avoid")
                        if isinstance(avoid_terms, list):
                            if len(avoid_terms) > 100:
                                issues.append({
                                    "severity": "error",
                                    "code": "TOO_MANY_AVOID_TERMS",
                                    "ref_key": rule.get("rule_key"),
                                    "message": f"Term map entry exceeds 100 avoid terms (has {len(avoid_terms)})",
                                })
                            for term in avoid_terms:
                                if isinstance(term, str) and len(term) > 100:
                                    issues.append({
                                        "severity": "error",
                                        "code": "TERM_TOO_LONG",
                                        "ref_key": rule.get("rule_key"),
                                        "message": f"Term map avoid term exceeds 100 characters: '{term[:50]}...'",
                                    })
                        prefer = entry.get("prefer")
                        if isinstance(prefer, str) and len(prefer) > 100:
                            issues.append({
                                "severity": "error",
                                "code": "TERM_TOO_LONG",
                                "ref_key": rule.get("rule_key"),
                                "message": f"Term map prefer term exceeds 100 characters: '{prefer[:50]}...'",
                            })
        elif check_type == "phrase_list":
            phrases = config.get("phrases")
            if isinstance(phrases, list):
                if len(phrases) > 100:
                    issues.append({
                        "severity": "error",
                        "code": "TOO_MANY_PHRASES",
                        "ref_key": rule.get("rule_key"),
                        "message": f"Phrase list rule {rule.get('rule_key')} exceeds 100 phrases (has {len(phrases)})",
                    })
                for phrase in phrases:
                    if isinstance(phrase, str) and len(phrase) > 100:
                        issues.append({
                            "severity": "error",
                            "code": "PHRASE_TOO_LONG",
                            "ref_key": rule.get("rule_key"),
                            "message": f"Phrase exceeds 100 characters: '{phrase[:50]}...'",
                        })
        elif check_type == "missing_alt_text":
            generic = config.get("generic")
            if isinstance(generic, list):
                if len(generic) > 100:
                    issues.append({
                        "severity": "error",
                        "code": "TOO_MANY_GENERIC_TERMS",
                        "ref_key": rule.get("rule_key"),
                        "message": f"Missing alt text rule {rule.get('rule_key')} exceeds 100 generic terms (has {len(generic)})",
                    })
        elif check_type == "required_disclosure":
            when_any = config.get("when_any")
            if isinstance(when_any, list):
                if len(when_any) > 100:
                    issues.append({
                        "severity": "error",
                        "code": "TOO_MANY_WHEN_ANY_TERMS",
                        "ref_key": rule.get("rule_key"),
                        "message": f"Required disclosure rule {rule.get('rule_key')} exceeds 100 when_any terms (has {len(when_any)})",
                    })
            require_any = config.get("require_any")
            if isinstance(require_any, list):
                if len(require_any) > 100:
                    issues.append({
                        "severity": "error",
                        "code": "TOO_MANY_REQUIRE_ANY_TERMS",
                        "ref_key": rule.get("rule_key"),
                        "message": f"Required disclosure rule {rule.get('rule_key')} exceeds 100 require_any terms (has {len(require_any)})",
                    })

    # Calculate prompt size estimate using validated_rules and validated_facts
    # Safe to use .get() on validated dicts; non-strings handled by safe_len
    def safe_len(value):
        """Safely get length of a string value, returning 0 for non-strings."""
        if isinstance(value, str):
            return len(value)
        return 0

    total_chars = sum(
        safe_len(r.get("guideline_text")) for r in validated_rules
    ) + sum(
        safe_len(f.get("statement")) + safe_len(f.get("source_note")) for f in validated_facts
    )
    prompt_cap = 24000  # From REVIEW_ENGINE.md

    if total_chars > prompt_cap:
        issues.append({
            "severity": "error",
            "code": "KIT_TOO_LARGE",
            "ref_key": None,
            "message": f"Kit exceeds prompt character cap ({total_chars} > {prompt_cap})",
        })

    # Count rule types using validated_rules for consistency
    llm_rules = sum(1 for r in validated_rules if r.get("check_kind") == "llm")
    deterministic_rules = sum(1 for r in validated_rules if r.get("check_kind") == "deterministic")

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
        "rules": len(validated_rules),
        "facts": len(validated_facts),
        "llm_rules": llm_rules,
        "deterministic_rules": deterministic_rules,
        "prompt_chars_estimate": total_chars,
        "prompt_chars_cap": 24000,
    }

    return {
        "ok": ok,
        "issues": issues_output,
        "stats": stats,
        "warnings": warnings,
    }
