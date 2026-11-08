"""Tests for deterministic checks."""

import pytest
from app.checks import (
    run_deterministic_checks,
    TermMapCheck,
    PhraseListCheck,
    MissingAltTextCheck,
    RequiredDisclosureCheck,
    DeterministicCheckResult,
    SkippedCheck,
)
from app.checks.deterministic import RuleConfig, check_map
from app.models.pipeline import DeterministicFindingCandidate


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

def make_rule_config(
    check: str,
    config: dict,
    rule_key: str = "TEST-01",
    category: str = "terminology",
    severity: str = "medium",
    guideline_text: str = "Test guideline",
    needs_reviewer: bool = False,
) -> RuleConfig:
    """Create a RuleConfig for testing."""
    return RuleConfig(
        check=check,
        config=config,
        rule_key=rule_key,
        category=category,
        severity=severity,
        guideline_text=guideline_text,
        needs_reviewer=needs_reviewer,
    )


# =============================================================================
# TermMapCheck Tests
# =============================================================================

class TestTermMapCheck:
    """Tests for TermMapCheck."""

    def test_basic_term_map(self):
        """Test basic term mapping with single avoid term."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "We should utilize this feature."
        candidates = checker.find_matches(text)

        assert len(candidates) == 1
        assert candidates[0].quote == "utilize"
        assert candidates[0].suggestion == "use"
        assert candidates[0].ref_key == "TEST-01"
        assert candidates[0].start_offset == 10
        assert candidates[0].end_offset == 17

    def test_multiple_avoid_terms(self):
        """Test multiple avoid terms mapping to same preferred term."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize", "leverage"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "We should utilize and leverage this."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        assert candidates[0].quote == "utilize"
        assert candidates[0].suggestion == "use"
        assert candidates[1].quote == "leverage"
        assert candidates[1].suggestion == "use"

    def test_capitalisation_matching(self):
        """Test that suggestion matches first-letter capitalisation."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "Utilize this. Do not utilize that."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        # First occurrence is capitalized
        assert candidates[0].quote == "Utilize"
        assert candidates[0].suggestion == "Use"
        # Second occurrence is lowercase
        assert candidates[1].quote == "utilize"
        assert candidates[1].suggestion == "use"

    def test_word_boundary_matching(self):
        """Test that matches only occur at word boundaries."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["use"], "prefer": "utilize"}]},
        )
        checker = TermMapCheck(rule)
        text = "We should use this. The user likes it."
        candidates = checker.find_matches(text)

        # "use" as standalone word matches, but not inside "user"
        assert len(candidates) == 1
        assert candidates[0].quote == "use"

    def test_multiple_entries(self):
        """Test multiple entries in term map."""
        rule = make_rule_config(
            check="term_map",
            config={
                "entries": [
                    {"avoid": ["utilize"], "prefer": "use"},
                    {"avoid": ["synergy"], "prefer": "collaboration"},
                ]
            },
        )
        checker = TermMapCheck(rule)
        text = "We should utilize synergy."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        suggestions = {c.quote: c.suggestion for c in candidates}
        assert suggestions["utilize"] == "use"
        assert suggestions["synergy"] == "collaboration"

    def test_empty_entries(self):
        """Test empty entries list produces no candidates."""
        rule = make_rule_config(check="term_map", config={"entries": []})
        checker = TermMapCheck(rule)
        text = "We should utilize this."
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "UTILIZE Utilize utilize"
        candidates = checker.find_matches(text)

        assert len(candidates) == 3
        # All should have appropriate capitalisation in suggestion
        assert candidates[0].suggestion == "Use"
        assert candidates[1].suggestion == "Use"
        assert candidates[2].suggestion == "use"

    def test_special_characters_in_terms(self):
        """Test terms with special regex characters."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["C++", "C#"], "prefer": "C"}]},
        )
        checker = TermMapCheck(rule)
        text = "I know C++ and C#."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        assert candidates[0].quote == "C++"
        assert candidates[1].quote == "C#"

    def test_overlapping_matches_different_rules(self):
        """Test that overlapping matches from different rules are all found."""
        rule1 = make_rule_config(
            rule_key="TERM-01",
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        rule2 = make_rule_config(
            rule_key="TERM-02",
            check="term_map",
            config={"entries": [{"avoid": ["utilize this"], "prefer": "do this"}]},
        )
        checker1 = TermMapCheck(rule1)
        checker2 = TermMapCheck(rule2)
        text = "Please utilize this feature."

        candidates1 = checker1.find_matches(text)
        candidates2 = checker2.find_matches(text)

        # Both should find matches
        assert len(candidates1) == 1
        assert len(candidates2) == 1


# =============================================================================
# PhraseListCheck Tests
# =============================================================================

class TestPhraseListCheck:
    """Tests for PhraseListCheck."""

    def test_basic_phrase_list(self):
        """Test basic phrase matching."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["guaranteed", "100% secure"]},
        )
        checker = PhraseListCheck(rule)
        text = "This is guaranteed to work. It is 100% secure."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        assert candidates[0].quote == "guaranteed"
        assert candidates[1].quote == "100% secure"
        assert candidates[0].suggestion is None
        assert candidates[1].suggestion is None

    def test_word_boundary_matching(self):
        """Test phrase matching respects word boundaries."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["best"]},
        )
        checker = PhraseListCheck(rule)
        text = "This is the best. This is the bestest."
        candidates = checker.find_matches(text)

        # "best" matches, "bestest" does not
        assert len(candidates) == 1
        assert candidates[0].quote == "best"

    def test_phrase_with_special_chars(self):
        """Test phrases with special characters."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["#1", "100%", "best-in-class"]},
        )
        checker = PhraseListCheck(rule)
        text = "We are #1 and 100% sure. Our best-in-class service."
        candidates = checker.find_matches(text)

        assert len(candidates) == 3

    def test_empty_phrases_list(self):
        """Test empty phrases list produces no candidates."""
        rule = make_rule_config(check="phrase_list", config={"phrases": []})
        checker = PhraseListCheck(rule)
        text = "This is guaranteed."
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_case_insensitive(self):
        """Test case-insensitive phrase matching."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["guaranteed"]},
        )
        checker = PhraseListCheck(rule)
        text = "GUARANTEED Guaranteed guaranteed"
        candidates = checker.find_matches(text)

        assert len(candidates) == 3

    def test_multiple_occurrences(self):
        """Test multiple occurrences of same phrase."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["guaranteed"]},
        )
        checker = PhraseListCheck(rule)
        text = "guaranteed and guaranteed again"
        candidates = checker.find_matches(text)

        assert len(candidates) == 2


# =============================================================================
# MissingAltTextCheck Tests
# =============================================================================

class TestMissingAltTextCheck:
    """Tests for MissingAltTextCheck."""

    def test_missing_alt_text_empty(self):
        """Test detection of empty alt text."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here is an image: ![](image.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1
        assert candidates[0].quote == "![](image.png)"
        assert candidates[0].suggestion is None

    def test_missing_alt_text_whitespace(self):
        """Test detection of whitespace-only alt text."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here is an image: ![   ](image.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1

    def test_alt_text_too_short(self):
        """Test detection of alt text shorter than min_length."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 10, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here is an image: ![short](image.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1

    def test_generic_alt_text(self):
        """Test detection of generic alt text."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo", "picture", "screenshot"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here is an image: ![image](photo.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1

    def test_generic_alt_text_case_insensitive(self):
        """Test generic alt text matching is case-insensitive."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here: ![IMAGE](a.png) and ![Photo](b.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 2

    def test_valid_alt_text(self):
        """Test that valid alt text produces no findings."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "Here is a chart: ![quarterly revenue chart](chart.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_multiple_images(self):
        """Test multiple images with mixed validity."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "![image](a.png) ![valid description](b.png) ![](c.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 2  # First and third are invalid

    def test_no_images(self):
        """Test text with no images produces no findings."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "This is just text with no images."
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_min_length_boundary(self):
        """Test min_length boundary condition."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        # Exactly min_length should pass
        text = "![abcd](img.png) ![abcde](img2.png)"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1  # First is 4 chars (< 5), second is 5 chars (>= 5)

    def test_malformed_markdown(self):
        """Test that malformed markdown doesn't crash."""
        rule = make_rule_config(
            check="missing_alt_text",
            config={"min_length": 5, "generic": ["image", "photo"]},
        )
        checker = MissingAltTextCheck(rule)
        text = "![missing close paren ![also bad"
        candidates = checker.find_matches(text)

        # Should handle gracefully, likely finding nothing
        assert len(candidates) == 0


# =============================================================================
# RequiredDisclosureCheck Tests
# =============================================================================

class TestRequiredDisclosureCheck:
    """Tests for RequiredDisclosureCheck."""

    def test_trigger_without_disclosure(self):
        """Test finding when trigger appears without required disclosure."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored", "in collaboration with"], "require_any": ["#ad", "paid partnership"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "This post is sponsored by BrandX."
        candidates = checker.find_matches(text)

        assert len(candidates) == 1
        assert candidates[0].quote == "sponsored"
        assert candidates[0].suggestion is None

    def test_trigger_with_disclosure_present(self):
        """Test no finding when required disclosure is present."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored"], "require_any": ["#ad"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "This post is sponsored. #ad"
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_multiple_triggers(self):
        """Test multiple trigger phrases."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored", "partner"], "require_any": ["#ad"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "This is sponsored and a partner post."
        candidates = checker.find_matches(text)

        assert len(candidates) == 2
        quotes = {c.quote for c in candidates}
        assert quotes == {"sponsored", "partner"}

    def test_no_trigger(self):
        """Test no finding when no trigger phrase appears."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored"], "require_any": ["#ad"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "This is a regular post."
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_disclosure_elsewhere_in_text(self):
        """Test disclosure anywhere in text satisfies requirement."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored"], "require_any": ["#ad"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "#ad This post is sponsored."
        candidates = checker.find_matches(text)

        assert len(candidates) == 0

    def test_word_boundary_matching(self):
        """Test trigger matching respects word boundaries."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsor"], "require_any": ["#ad"]},
        )
        checker = RequiredDisclosureCheck(rule)
        text = "This is a sponsor. The sponsorship deal."  # "sponsorship" shouldn't match "sponsor"
        candidates = checker.find_matches(text)

        assert len(candidates) == 1
        assert candidates[0].quote == "sponsor"

    def test_multiple_required_disclosures_any_satisfies(self):
        """Test that any one required disclosure satisfies the requirement."""
        rule = make_rule_config(
            check="required_disclosure",
            config={"when_any": ["sponsored"], "require_any": ["#ad", "paid partnership"]},
        )
        checker = RequiredDisclosureCheck(rule)
        # Only #ad present - should satisfy
        text = "This post is sponsored. #ad"
        candidates = checker.find_matches(text)
        assert len(candidates) == 0

        # Only paid partnership present - should satisfy
        text2 = "This post is sponsored. paid partnership"
        candidates2 = checker.find_matches(text2)
        assert len(candidates2) == 0


# =============================================================================
# Integration Tests - run_deterministic_checks
# =============================================================================

class TestRunDeterministicChecks:
    """Integration tests for run_deterministic_checks."""

    def test_multiple_rule_types(self):
        """Test running multiple rule types together."""
        rules = [
            make_rule_config(
                rule_key="TERM-01",
                check="term_map",
                config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
            ),
            make_rule_config(
                rule_key="PHRASE-01",
                check="phrase_list",
                config={"phrases": ["guaranteed"]},
            ),
            make_rule_config(
                rule_key="ALT-01",
                check="missing_alt_text",
                config={"min_length": 5, "generic": ["image"]},
            ),
            make_rule_config(
                rule_key="DISC-01",
                check="required_disclosure",
                config={"when_any": ["sponsored"], "require_any": ["#ad"]},
            ),
        ]

        text = "We should utilize this guaranteed product. ![image](img.png) This is sponsored."
        result = run_deterministic_checks(text, rules)

        assert isinstance(result, DeterministicCheckResult)
        assert len(result.candidates) == 4
        ref_keys = {c.ref_key for c in result.candidates}
        assert ref_keys == {"TERM-01", "PHRASE-01", "ALT-01", "DISC-01"}
        assert len(result.skipped_checks) == 0

    def test_unknown_check_type_skipped(self):
        """Test unknown check type produces skipped check warning."""
        rules = [
            make_rule_config(
                rule_key="UNKNOWN-01",
                check="unknown_type",
                config={},
            ),
            make_rule_config(
                rule_key="TERM-01",
                check="term_map",
                config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
            ),
        ]

        text = "We should utilize this."
        result = run_deterministic_checks(text, rules)

        assert isinstance(result, DeterministicCheckResult)
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "TERM-01"
        assert len(result.skipped_checks) == 1
        skipped = result.skipped_checks[0]
        assert skipped.rule_key == "UNKNOWN-01"
        assert skipped.check_type == "unknown_type"
        assert "Unknown check type" in skipped.reason

    def test_empty_rules(self):
        """Test empty rules list produces no candidates."""
        result = run_deterministic_checks("any text", [])
        assert isinstance(result, DeterministicCheckResult)
        assert len(result.candidates) == 0
        assert len(result.skipped_checks) == 0

    def test_order_preserved(self):
        """Test that candidates are ordered by rule order and then by offset."""
        rules = [
            make_rule_config(
                rule_key="A-01",
                check="term_map",
                config={"entries": [{"avoid": ["b"], "prefer": "x"}]},
            ),
            make_rule_config(
                rule_key="B-01",
                check="term_map",
                config={"entries": [{"avoid": ["a"], "prefer": "y"}]},
            ),
        ]

        text = "a b a b"
        result = run_deterministic_checks(text, rules)

        # Rule A finds "b" at positions 2 and 6
        # Rule B finds "a" at positions 0 and 4
        # Order should be: A's matches first, then B's matches
        assert result.candidates[0].ref_key == "A-01"
        assert result.candidates[1].ref_key == "A-01"
        assert result.candidates[2].ref_key == "B-01"
        assert result.candidates[3].ref_key == "B-01"

    def test_valid_check_with_no_findings_distinguishable_from_skipped(self):
        """Test that a valid check with no findings is distinguishable from a skipped check."""
        rules = [
            make_rule_config(
                rule_key="VALID-NO-FINDINGS",
                check="phrase_list",
                config={"phrases": ["nonexistent"]},
            ),
            make_rule_config(
                rule_key="INVALID-CONFIG",
                check="term_map",
                config={"entries": [{"avoid": "not-a-list", "prefer": "use"}]},
            ),
        ]

        text = "Some text without the phrase."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 0
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "INVALID-CONFIG"
        # VALID-NO-FINDINGS ran and found nothing - not in skipped_checks


# =============================================================================
# Configuration Validation Tests
# =============================================================================

class TestConfigurationValidation:
    """Tests for configuration validation in each check type."""

    # term_map validation
    def test_term_map_missing_entries(self):
        """Test term_map with missing entries field."""
        rule = make_rule_config(check="term_map", config={})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'entries' field" in str(exc.value)

    def test_term_map_entries_not_list(self):
        """Test term_map with entries as non-list."""
        rule = make_rule_config(check="term_map", config={"entries": "not-a-list"})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'entries' must be a list" in str(exc.value)

    def test_term_map_empty_entries(self):
        """Test term_map with empty entries list."""
        rule = make_rule_config(check="term_map", config={"entries": []})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'entries' list cannot be empty" in str(exc.value)

    def test_term_map_entry_not_dict(self):
        """Test term_map with entry as non-dict."""
        rule = make_rule_config(check="term_map", config={"entries": ["not-a-dict"]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Entry 0 must be an object" in str(exc.value)

    def test_term_map_missing_avoid(self):
        """Test term_map entry missing avoid field."""
        rule = make_rule_config(check="term_map", config={"entries": [{"prefer": "use"}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "missing required 'avoid' field" in str(exc.value)

    def test_term_map_avoid_not_list(self):
        """Test term_map entry with avoid as non-list."""
        rule = make_rule_config(check="term_map", config={"entries": [{"avoid": "utilize", "prefer": "use"}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'avoid' must be a list" in str(exc.value)

    def test_term_map_empty_avoid(self):
        """Test term_map entry with empty avoid list."""
        rule = make_rule_config(check="term_map", config={"entries": [{"avoid": [], "prefer": "use"}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'avoid' list cannot be empty" in str(exc.value)

    def test_term_map_avoid_non_string(self):
        """Test term_map entry with non-string avoid term."""
        rule = make_rule_config(check="term_map", config={"entries": [{"avoid": ["utilize", 123], "prefer": "use"}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'avoid[1]' must be a non-empty string" in str(exc.value)

    def test_term_map_missing_prefer(self):
        """Test term_map entry missing prefer field."""
        rule = make_rule_config(check="term_map", config={"entries": [{"avoid": ["utilize"]}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "missing required 'prefer' field" in str(exc.value)

    def test_term_map_prefer_not_string(self):
        """Test term_map entry with prefer as non-string."""
        rule = make_rule_config(check="term_map", config={"entries": [{"avoid": ["utilize"], "prefer": 123}]})
        checker = TermMapCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'prefer' must be a non-empty string" in str(exc.value)

    # phrase_list validation
    def test_phrase_list_missing_phrases(self):
        """Test phrase_list with missing phrases field."""
        rule = make_rule_config(check="phrase_list", config={})
        checker = PhraseListCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'phrases' field" in str(exc.value)

    def test_phrase_list_phrases_not_list(self):
        """Test phrase_list with phrases as non-list."""
        rule = make_rule_config(check="phrase_list", config={"phrases": "guaranteed"})
        checker = PhraseListCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'phrases' must be a list" in str(exc.value)

    def test_phrase_list_empty_phrases(self):
        """Test phrase_list with empty phrases list."""
        rule = make_rule_config(check="phrase_list", config={"phrases": []})
        checker = PhraseListCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'phrases' list cannot be empty" in str(exc.value)

    def test_phrase_list_non_string_phrase(self):
        """Test phrase_list with non-string phrase."""
        rule = make_rule_config(check="phrase_list", config={"phrases": ["guaranteed", 123]})
        checker = PhraseListCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'phrases[1]' must be a non-empty string" in str(exc.value)

    # missing_alt_text validation
    def test_missing_alt_text_missing_min_length(self):
        """Test missing_alt_text with missing min_length field."""
        rule = make_rule_config(check="missing_alt_text", config={"generic": ["image"]})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'min_length' field" in str(exc.value)

    def test_missing_alt_text_min_length_not_int(self):
        """Test missing_alt_text with min_length as non-int."""
        rule = make_rule_config(check="missing_alt_text", config={"min_length": "five", "generic": ["image"]})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'min_length' must be an integer" in str(exc.value)

    def test_missing_alt_text_min_length_not_positive(self):
        """Test missing_alt_text with min_length <= 0."""
        rule = make_rule_config(check="missing_alt_text", config={"min_length": 0, "generic": ["image"]})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'min_length' must be positive" in str(exc.value)

    def test_missing_alt_text_missing_generic(self):
        """Test missing_alt_text with missing generic field."""
        rule = make_rule_config(check="missing_alt_text", config={"min_length": 5})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'generic' field" in str(exc.value)

    def test_missing_alt_text_generic_not_list(self):
        """Test missing_alt_text with generic as non-list."""
        rule = make_rule_config(check="missing_alt_text", config={"min_length": 5, "generic": "image"})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'generic' must be a list" in str(exc.value)

    def test_missing_alt_text_generic_non_string(self):
        """Test missing_alt_text with non-string generic term."""
        rule = make_rule_config(check="missing_alt_text", config={"min_length": 5, "generic": ["image", 123]})
        checker = MissingAltTextCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'generic[1]' must be a non-empty string" in str(exc.value)

    # required_disclosure validation
    def test_required_disclosure_missing_when_any(self):
        """Test required_disclosure with missing when_any field."""
        rule = make_rule_config(check="required_disclosure", config={"require_any": ["#ad"]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'when_any' field" in str(exc.value)

    def test_required_disclosure_when_any_not_list(self):
        """Test required_disclosure with when_any as non-list."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": "sponsored", "require_any": ["#ad"]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'when_any' must be a list" in str(exc.value)

    def test_required_disclosure_empty_when_any(self):
        """Test required_disclosure with empty when_any list."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": [], "require_any": ["#ad"]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'when_any' list cannot be empty" in str(exc.value)

    def test_required_disclosure_when_any_non_string(self):
        """Test required_disclosure with non-string when_any term."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": ["sponsored", 123], "require_any": ["#ad"]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'when_any[1]' must be a non-empty string" in str(exc.value)

    def test_required_disclosure_missing_require_any(self):
        """Test required_disclosure with missing require_any field."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": ["sponsored"]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "Missing required 'require_any' field" in str(exc.value)

    def test_required_disclosure_require_any_not_list(self):
        """Test required_disclosure with require_any as non-list."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": ["sponsored"], "require_any": "#ad"})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'require_any' must be a list" in str(exc.value)

    def test_required_disclosure_empty_require_any(self):
        """Test required_disclosure with empty require_any list."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": ["sponsored"], "require_any": []})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'require_any' list cannot be empty" in str(exc.value)

    def test_required_disclosure_require_any_non_string(self):
        """Test required_disclosure with non-string require_any term."""
        rule = make_rule_config(check="required_disclosure", config={"when_any": ["sponsored"], "require_any": ["#ad", 123]})
        checker = RequiredDisclosureCheck(rule)
        with pytest.raises(ValueError) as exc:
            checker.validate_config()
        assert "'require_any[1]' must be a non-empty string" in str(exc.value)


# =============================================================================
# Skipped Check Integration Tests
# =============================================================================

class TestSkippedChecks:
    """Tests for skipped check behavior in run_deterministic_checks."""

    def test_malformed_term_map_skipped(self):
        """Test malformed term_map config creates skipped check."""
        rules = [
            make_rule_config(
                rule_key="BAD-TERM",
                check="term_map",
                config={"entries": [{"avoid": "not-a-list", "prefer": "use"}]},
            ),
            make_rule_config(
                rule_key="GOOD-TERM",
                check="term_map",
                config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
            ),
        ]
        text = "We should utilize this."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-TERM"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-TERM"
        assert result.skipped_checks[0].check_type == "term_map"
        assert "avoid" in result.skipped_checks[0].reason

    def test_malformed_phrase_list_skipped(self):
        """Test malformed phrase_list config creates skipped check."""
        rules = [
            make_rule_config(
                rule_key="BAD-PHRASE",
                check="phrase_list",
                config={"phrases": "not-a-list"},
            ),
            make_rule_config(
                rule_key="GOOD-PHRASE",
                check="phrase_list",
                config={"phrases": ["guaranteed"]},
            ),
        ]
        text = "This is guaranteed."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-PHRASE"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-PHRASE"

    def test_malformed_missing_alt_text_skipped(self):
        """Test malformed missing_alt_text config creates skipped check."""
        rules = [
            make_rule_config(
                rule_key="BAD-ALT",
                check="missing_alt_text",
                config={"min_length": "five", "generic": ["image"]},
            ),
            make_rule_config(
                rule_key="GOOD-ALT",
                check="missing_alt_text",
                config={"min_length": 5, "generic": ["image"]},
            ),
        ]
        text = "![image](img.png)"
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-ALT"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-ALT"

    def test_malformed_required_disclosure_skipped(self):
        """Test malformed required_disclosure config creates skipped check."""
        rules = [
            make_rule_config(
                rule_key="BAD-DISC",
                check="required_disclosure",
                config={"when_any": "sponsored", "require_any": "#ad"},
            ),
            make_rule_config(
                rule_key="GOOD-DISC",
                check="required_disclosure",
                config={"when_any": ["sponsored"], "require_any": ["#ad"]},
            ),
        ]
        text = "This is sponsored."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-DISC"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-DISC"

    def test_valid_check_runs_when_other_skipped(self):
        """Test that a valid check still executes when another check is skipped."""
        rules = [
            make_rule_config(
                rule_key="BAD",
                check="term_map",
                config={"entries": [{"avoid": "bad", "prefer": "good"}]},
            ),
            make_rule_config(
                rule_key="GOOD",
                check="phrase_list",
                config={"phrases": ["guaranteed"]},
            ),
        ]
        text = "This is guaranteed."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD"
        assert len(result.skipped_checks) == 1

    def test_unknown_check_type_observable(self):
        """Test unknown check types produce skipped check with reason."""
        rules = [
            make_rule_config(
                rule_key="UNKNOWN-01",
                check="unknown_type",
                config={},
            ),
        ]
        text = "any text"
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 0
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "UNKNOWN-01"
        assert result.skipped_checks[0].check_type == "unknown_type"
        assert "Unknown check type" in result.skipped_checks[0].reason

    def test_valid_check_with_no_findings_not_skipped(self):
        """Test that a valid check with no findings is NOT in skipped_checks."""
        rules = [
            make_rule_config(
                rule_key="VALID-NO-MATCH",
                check="phrase_list",
                config={"phrases": ["nonexistent"]},
            ),
        ]
        text = "Some text without the phrase."
        result = run_deterministic_checks(text, rules)

        assert len(result.candidates) == 0
        assert len(result.skipped_checks) == 0  # Valid check ran, found nothing


# =============================================================================
# Exception Isolation Tests
# =============================================================================

class TestExceptionIsolation:
    """Tests for exception isolation in run_deterministic_checks."""

    def test_constructor_failure_skips_only_that_rule(self):
        """Test that a check class constructor failure skips only that rule."""
        
        # Create a check class that fails in __init__
        class FailingConstructorCheck:
            check_name = "failing_constructor"
            
            def __init__(self, rule):
                raise RuntimeError("Constructor failed intentionally")
            
            def validate_config(self):
                pass
            
            def find_matches(self, text):
                return []
            
            def _make_candidate(self, quote, start_offset, end_offset, suggestion=None):
                pass
            
            def _build_explanation(self, matched_text):
                pass
        
        # We need to test by creating a check that will be used via the check map
        # Since we can't easily patch the internal check_map, we test the
        # constructor isolation by creating a subclass that fails in __init__
        # and testing through a custom runner call
        
        from engine.app.checks.deterministic import run_deterministic_checks, RuleConfig
        from engine.app.models.pipeline import DeterministicFindingCandidate
        
        # Create a minimal check class that fails in constructor
        from engine.app.checks.deterministic import DeterministicCheck
        from engine.app.checks.deterministic import check_map
        
        class FailingConstructorCheck(DeterministicCheck):
            check_name = "failing_constructor"
            
            def __init__(self, rule):
                super().__init__(rule)
                raise RuntimeError("Constructor failed intentionally")
            
            def validate_config(self):
                pass
            
            def find_matches(self, text):
                return []
        
        # Temporarily add to check_map
        check_map["failing_constructor"] = FailingConstructorCheck
        try:
            rules = [
                make_rule_config(
                    rule_key="BAD-CONSTRUCTOR",
                    check="failing_constructor",
                    config={},
                ),
                make_rule_config(
                    rule_key="GOOD-AFTER-BAD",
                    check="phrase_list",
                    config={"phrases": ["guaranteed"]},
                ),
            ]
            text = "This is guaranteed."
            
            result = run_deterministic_checks(text, rules)
        finally:
            del check_map["failing_constructor"]
        
        # Should skip the bad one, run the good one
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-AFTER-BAD"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-CONSTRUCTOR"
        assert "Check construction error" in result.skipped_checks[0].reason
        assert "RuntimeError" in result.skipped_checks[0].reason

    def test_execution_valueerror_classified_as_execution_error(self):
        """Test that ValueError from find_matches is execution error, not config error."""
        
        from engine.app.checks.deterministic import check_map, DeterministicCheck
        
        class ExecutionValueErrorCheck(DeterministicCheck):
            check_name = "execution_valueerror"
            
            def __init__(self, rule):
                super().__init__(rule)
            
            def validate_config(self):
                pass
            
            def find_matches(self, text):
                raise ValueError("SENSITIVE DRAFT CONTENT: secret123")
        
        check_map["execution_valueerror"] = ExecutionValueErrorCheck
        try:
            rules = [
                make_rule_config(
                    rule_key="EXEC-VALUEERROR",
                    check="execution_valueerror",
                    config={"entries": [{"avoid": ["test"], "prefer": "x"}]},
                ),
                make_rule_config(
                    rule_key="GOOD-AFTER-EXEC-ERROR",
                    check="phrase_list",
                    config={"phrases": ["guaranteed"]},
                ),
            ]
            text = "This is guaranteed."
            
            result = run_deterministic_checks(text, rules)
        finally:
            del check_map["execution_valueerror"]
        
        # Should skip the execution error one, run the good one
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-AFTER-EXEC-ERROR"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "EXEC-VALUEERROR"
        # Should be classified as execution error, not config error
        assert "Check execution error" in result.skipped_checks[0].reason
        assert "ValueError" in result.skipped_checks[0].reason
        # Sensitive text must NOT be exposed
        assert "SENSITIVE" not in result.skipped_checks[0].reason
        assert "secret123" not in result.skipped_checks[0].reason
        assert "DRAFT CONTENT" not in result.skipped_checks[0].reason

    def test_execution_runtimeerror_classified_as_execution_error(self):
        """Test that RuntimeError from find_matches is execution error."""
        
        from engine.app.checks.deterministic import check_map, DeterministicCheck
        
        class ExecutionRuntimeErrorCheck(DeterministicCheck):
            check_name = "execution_runtimeerror"
            
            def __init__(self, rule):
                super().__init__(rule)
            
            def validate_config(self):
                pass
            
            def find_matches(self, text):
                raise RuntimeError("Execution failed")
        
        check_map["execution_runtimeerror"] = ExecutionRuntimeErrorCheck
        try:
            rules = [
                make_rule_config(
                    rule_key="EXEC-RUNTIMEERROR",
                    check="execution_runtimeerror",
                    config={"entries": [{"avoid": ["test"], "prefer": "x"}]},
                ),
                make_rule_config(
                    rule_key="GOOD-AFTER-EXEC-ERROR-2",
                    check="phrase_list",
                    config={"phrases": ["guaranteed"]},
                ),
            ]
            text = "This is guaranteed."
            
            result = run_deterministic_checks(text, rules)
        finally:
            del check_map["execution_runtimeerror"]
        
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-AFTER-EXEC-ERROR-2"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "EXEC-RUNTIMEERROR"
        assert "Check execution error" in result.skipped_checks[0].reason
        assert "RuntimeError" in result.skipped_checks[0].reason

    def test_config_valueerror_is_raw_validation_message(self):
        """Test that ValueError from validate_config produces raw validation message."""
        
        # Use existing validation - malformed term_map
        rules = [
            make_rule_config(
                rule_key="BAD-CONFIG",
                check="term_map",
                config={"entries": [{"avoid": "not-a-list", "prefer": "use"}]},
            ),
            make_rule_config(
                rule_key="GOOD-AFTER-CONFIG",
                check="phrase_list",
                config={"phrases": ["guaranteed"]},
            ),
        ]
        text = "This is guaranteed."
        
        result = run_deterministic_checks(text, rules)
        
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-AFTER-CONFIG"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "BAD-CONFIG"
        # Config ValueError gives raw validation message
        assert "avoid" in result.skipped_checks[0].reason
        assert "list" in result.skipped_checks[0].reason
        # Should NOT be execution error
        assert "Check execution error" not in result.skipped_checks[0].reason
        # Should NOT be "Check configuration error" prefix (that's for non-ValueError config errors)
        assert "Check configuration error" not in result.skipped_checks[0].reason

    def test_config_non_valueerror_classified_as_config_error(self):
        """Test that non-ValueError from validate_config is config error with prefix."""
        
        from engine.app.checks.deterministic import check_map, DeterministicCheck
        
        class ConfigTypeErrorCheck(DeterministicCheck):
            check_name = "config_typeerror"
            
            def __init__(self, rule):
                super().__init__(rule)
            
            def validate_config(self):
                raise TypeError("Some type error")
            
            def find_matches(self, text):
                return []
        
        check_map["config_typeerror"] = ConfigTypeErrorCheck
        try:
            rules = [
                make_rule_config(
                    rule_key="CONFIG-TYPEERROR",
                    check="config_typeerror",
                    config={},
                ),
                make_rule_config(
                    rule_key="GOOD-AFTER-CONFIG-TE",
                    check="phrase_list",
                    config={"phrases": ["guaranteed"]},
                ),
            ]
            text = "This is guaranteed."
            
            result = run_deterministic_checks(text, rules)
        finally:
            del check_map["config_typeerror"]
        
        assert len(result.candidates) == 1
        assert result.candidates[0].ref_key == "GOOD-AFTER-CONFIG-TE"
        assert len(result.skipped_checks) == 1
        assert result.skipped_checks[0].rule_key == "CONFIG-TYPEERROR"
        # Non-ValueError config errors get "Check configuration error" prefix
        assert "Check configuration error" in result.skipped_checks[0].reason
        assert "TypeError" in result.skipped_checks[0].reason

    def test_malformed_config_behavior_unchanged(self):
        """Test that existing malformed configuration behavior is unchanged."""
        
        # All the existing validation tests should still pass
        # This test just verifies the overall behavior pattern
        test_cases = [
            ("term_map", {"entries": "not-a-list"}),
            ("phrase_list", {"phrases": "not-a-list"}),
            ("missing_alt_text", {"min_length": "five", "generic": ["img"]}),
            ("required_disclosure", {"when_any": "x", "require_any": "y"}),
        ]
        
        for check_type, bad_config in test_cases:
            rules = [
                make_rule_config(
                    rule_key=f"BAD-{check_type.upper()}",
                    check=check_type,
                    config=bad_config,
                ),
                make_rule_config(
                    rule_key=f"GOOD-{check_type.upper()}",
                    check="phrase_list",
                    config={"phrases": ["guaranteed"]},
                ),
            ]
            text = "This is guaranteed."
            result = run_deterministic_checks(text, rules)
            
            # Good check should run
            assert len(result.candidates) == 1
            assert result.candidates[0].ref_key == f"GOOD-{check_type.upper()}"
            # Bad check should be skipped
            assert len(result.skipped_checks) == 1
            assert result.skipped_checks[0].rule_key == f"BAD-{check_type.upper()}"
            # Config ValueError gives raw message (no prefix)
            # Should NOT be execution error
            assert "Check execution error" not in result.skipped_checks[0].reason
            # Should NOT be "Check configuration error" prefix
            assert "Check configuration error" not in result.skipped_checks[0].reason


# =============================================================================
# Unicode Offset Tests
# =============================================================================

class TestUnicodeOffsets:
    """Tests for Unicode code-point offset correctness."""

    def test_ascii_text_offsets(self):
        """Test offsets are correct for ASCII text."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "We utilize this."
        candidates = checker.find_matches(text)

        assert candidates[0].start_offset == 3
        assert candidates[0].end_offset == 10
        # Verify quote matches text slice
        assert text[candidates[0].start_offset:candidates[0].end_offset] == candidates[0].quote

    def test_unicode_emoji_offsets(self):
        """Test offsets are correct with emoji (multi-code-point)."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "We 😀 utilize this."
        candidates = checker.find_matches(text)

        # Emoji is 1 code point in Python 3, "We " = 3, emoji = 1, space = 1, so "utilize" starts at 5
        assert candidates[0].start_offset == 5
        assert candidates[0].end_offset == 12
        assert text[candidates[0].start_offset:candidates[0].end_offset] == candidates[0].quote

    def test_unicode_combining_chars(self):
        """Test offsets with combining characters."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["café"], "prefer": "cafe"}]},
        )
        checker = TermMapCheck(rule)
        # café with combining acute accent: c a f e ́ (5 code points)
        text = "I like café."
        candidates = checker.find_matches(text)

        assert candidates[0].start_offset == 7
        assert candidates[0].end_offset == 11  # 4 code points for café
        assert text[candidates[0].start_offset:candidates[0].end_offset] == candidates[0].quote

    def test_crlf_line_endings(self):
        """Test offsets with CRLF line endings (normalized to LF)."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "Line 1\r\nLine 2 utilize"
        candidates = checker.find_matches(text)

        # CRLF is 2 code points, LF is 1
        # The engine normalizes line endings to LF before checking
        # But we test on raw text - the offset should work on whatever text is passed
        assert candidates[0].quote == "utilize"
        assert text[candidates[0].start_offset:candidates[0].end_offset] == "utilize"


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================

class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_very_long_text(self):
        """Test with long text (near 20k char limit)."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["needle"]},
        )
        checker = PhraseListCheck(rule)
        text = "hay " * 5000 + "needle" + " hay" * 5000
        candidates = checker.find_matches(text)

        assert len(candidates) == 1

    def test_empty_text(self):
        """Test empty text produces no findings."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["anything"]},
        )
        checker = PhraseListCheck(rule)
        candidates = checker.find_matches("")

        assert len(candidates) == 0

    def test_whitespace_only_text(self):
        """Test whitespace-only text."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["test"]},
        )
        checker = PhraseListCheck(rule)
        candidates = checker.find_matches("   \n\t  ")

        assert len(candidates) == 0

    def test_quote_exact_match(self):
        """Test that quote exactly matches the source text slice."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["UTILIZE", "utilize"], "prefer": "use"}]},
        )
        checker = TermMapCheck(rule)
        text = "UTILIZE and utilize."
        candidates = checker.find_matches(text)

        for c in candidates:
            assert text[c.start_offset:c.end_offset] == c.quote

    def test_special_regex_chars_in_phrase_list(self):
        """Test phrase list handles regex special chars correctly."""
        rule = make_rule_config(
            check="phrase_list",
            config={"phrases": ["a.b", "a*b", "a+b", "a?b", "a[b]"]},
        )
        checker = PhraseListCheck(rule)
        text = "a.b a*b a+b a?b a[b]"
        candidates = checker.find_matches(text)

        assert len(candidates) == 5

    def test_special_regex_chars_in_term_map(self):
        """Test term map handles regex special chars correctly."""
        rule = make_rule_config(
            check="term_map",
            config={"entries": [{"avoid": ["a.b", "a*b"], "prefer": "x"}]},
        )
        checker = TermMapCheck(rule)
        text = "a.b a*b"
        candidates = checker.find_matches(text)

        assert len(candidates) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])