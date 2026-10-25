"""Fast, API-free tests for deterministic post-processing rules."""
from extraction import _normalize_date, _normalize_fields


def test_normalizes_unambiguous_space_separated_date():
    assert _normalize_date("28 8 26") == "28/08/2026"


def test_normalizes_iso_date():
    assert _normalize_date("2026-08-28") == "28/08/2026"


def test_preserves_ambiguous_date_for_review():
    assert _normalize_date("08/09/2026") == "08/09/2026"


def test_certificate_fields_require_explicit_yes():
    result = _normalize_fields({
        "Transfer Certificate": "attached",
        "Mark Sheets": "Yes",
        "Community Certificate": "",
        "Income Certificate": "checked",
    })
    assert result == {
        "Transfer Certificate": "-",
        "Mark Sheets": "Yes",
        "Community Certificate": "-",
        "Income Certificate": "Yes",
    }


def test_binary_and_gender_values_are_canonicalized():
    result = _normalize_fields({
        "Physically Challenged": "no",
        "First Graduate": "selected",
        "Gender": "F",
    })
    assert result["Physically Challenged"] == "No"
    assert result["First Graduate"] == "Yes"
    assert result["Gender"] == "Female"


def test_course_mapping_keeps_only_allowed_courses():
    result = _normalize_fields({"Course Applied": "B.Sc. English; B.Sc. Computer Science"})
    assert result["Course Applied"] == "B.Sc. Computer Science"
