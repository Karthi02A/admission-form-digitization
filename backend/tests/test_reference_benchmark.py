from datetime import datetime

from scripts.benchmark_extraction import (
    _comparable,
    _has_expected_value,
    _mismatch_cause,
    _reference_field,
    _reference_value,
    _reference_values,
)


def test_reference_labels_map_to_template_keys_without_using_student_values():
    assert _reference_field("Name") == "Student Name"
    assert _reference_field("Gender - Female") == "Gender"
    assert _reference_field("Proposed Study - B.Sc. Physics") == "Course Applied"
    assert _reference_field("Email ID - Student") == "Email"
    assert _reference_field("Income (as written, numeric)") == "Income"
    assert _reference_field("Community Certificate - Yes") == "Community Certificate"


def test_option_reference_values_come_from_selected_workbook_label():
    assert _reference_value(
        "Gender - Female", "Yes", "Gender"
    ) == "female"
    assert _reference_value(
        "Proposed Study - B.Sc. Physics", "Yes", "Course Applied"
    ) == "b sc physics"
    assert _reference_value(
        "First Graduate - Yes", "Yes", "First Graduate"
    ) == "yes"
    assert _reference_value(
        "Gender - Male", "No", "Gender"
    ) is None


def test_conflicting_selected_reference_options_are_excluded_as_ambiguous():
    expected, ambiguous = _reference_values(
        [
            ("Proposed Study - B.Sc. Physics", "Yes"),
            ("Proposed Study - B.Sc. Chemistry", "Yes"),
            ("Gender - Female", "Yes"),
        ]
    )

    assert "Course Applied" not in expected
    assert expected["Gender"] == "female"
    assert ambiguous == {"Course Applied"}


def test_reference_correction_notes_are_not_treated_as_fields():
    assert _reference_field("Roll number correction") is None
    assert _reference_field("Received Date - original text") is None
    assert _reference_field("Review notes") is None


def test_blank_markers_are_not_counted_as_reference_answers():
    assert not _has_expected_value("N/A")
    assert not _has_expected_value("—")
    assert _has_expected_value("31/07/2009")


def test_reference_date_comparison_normalizes_excel_and_form_formats():
    reference_date = datetime(2006, 3, 2)

    assert _comparable("02/03/2006", "Date of Birth") == _comparable(
        reference_date, "Date of Birth"
    )


def test_reference_comparison_normalizes_gender_and_course_formatting():
    assert _comparable("F", "Gender") == _comparable("Female", "Gender")
    assert _comparable(
        "B.Sc. Physics", "Course Applied"
    ) == _comparable("B Sc Physics", "Course Applied")


def test_diagnostic_cause_distinguishes_ocr_loss_from_mapping():
    assert _mismatch_cause(
        "Student Name", "Asha Raman", "", "Asha Raman", ""
    ) == "OCR recognition/coverage"
    assert _mismatch_cause(
        "Student Name", "Asha Raman", "", "", "Asha Raman"
    ) == "field mapping/layout"


def test_diagnostic_cause_identifies_invalid_reference_format():
    assert _mismatch_cause(
        "Date of Birth", "31/06/2006", "", "", ""
    ) == "validation"


def test_diagnostic_cause_identifies_checkbox_selection_ambiguity():
    assert _mismatch_cause(
        "Course Applied", "B.Sc. Physics", "", "", "B.Sc. Physics"
    ) == "checkbox/layout selection"
