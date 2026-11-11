"""Kit lint API endpoints."""
from fastapi import APIRouter, Depends, Path, status, HTTPException
from uuid import UUID
from datetime import date
import re

from app.auth.dependencies import AuthUser, get_current_user_single_org, require_owner
from app.auth.supabase import get_supabase_client
from app.checks.deterministic import check_map
from app.checks.deterministic import RuleConfig

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

    # Check: kit has at least one rule
    if not rules:
        issues.append({
            "severity": "error",
            "code": "EMPTY_KIT",
            "ref_key": None,
            "message": "Kit must have at least one rule",
        })

    # Validate all rules first (independently of check_kind)
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
                check_type = raw_config.get("check")

                if not isinstance(check_type, str) or check_type not in check_map:
                    issues.append({
                        "severity": "error",
                        "code": "UNKNOWN_CHECK_TYPE",
                        "ref_key": rule_key,
                        "message": f"Unknown deterministic check type: {check_type!r}",
                    })
                else:
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
    deterministic_rules_list = [r for r in rules if isinstance(r, dict) and r.get("check_kind") == "deterministic"]
    if len(deterministic_rules_list) > 50:
        issues.append({
            "severity": "error",
            "code": "TOO_MANY_DETERMINISTIC_RULES",
            "ref_key": None,
            "message": f"Kit exceeds maximum of 50 deterministic rules (has {len(deterministic_rules_list)})",
        })

    for rule in deterministic_rules_list:
        if not isinstance(rule, dict):
            continue

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

    # Calculate prompt size estimate (safely handle non-string guideline_text and non-dict rules/facts)
    def safe_len(value):
        """Safely get length of a string value, returning 0 for non-strings."""
        if isinstance(value, str):
            return len(value)
        return 0

    total_chars = sum(
        safe_len(r.get("guideline_text")) for r in rules if isinstance(r, dict)
    ) + sum(
        safe_len(f.get("statement")) + safe_len(f.get("source_note")) for f in facts if isinstance(f, dict)
    )
    prompt_cap = 24000  # From REVIEW_ENGINE.md

    if total_chars > prompt_cap:
        issues.append({
            "severity": "error",
            "code": "KIT_TOO_LARGE",
            "ref_key": None,
            "message": f"Kit exceeds prompt character cap ({total_chars} > {prompt_cap})",
        })

    # Count rule types (safely handle non-dict rules)
    llm_rules = sum(1 for r in rules if isinstance(r, dict) and r.get("check_kind") == "llm")
    deterministic_rules = sum(1 for r in rules if isinstance(r, dict) and r.get("check_kind") == "deterministic")

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
        "warnings": warnings,
    }