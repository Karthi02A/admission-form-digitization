from concurrent.futures import ThreadPoolExecutor
import io
import sys
import types
from pathlib import Path
from time import sleep

import cv2
import numpy as np
import pymupdf as fitz
from PIL import Image, ImageDraw

from app-old.services.extraction import _valid_value, map_fields
from app-old.services import ocr
from app-old.services.ocr import pdf_layout, pdf_text
from app-old.services.template_regions import handwriting_regions


def test_inline_values_only_use_their_own_labels():
    fields, quality = map_fields(
        "Name: Nivethitha R\n"
        "Father's / Guardian's Name: Ramesh Kumar\n"
        "Mother's Name: Sangeetha R\n"
        "Date of Birth: 30/06/2006\n"
        "Gender: F\n"
        "Mobile No student: 1234567890\n"
        "Email ID Student: student@example.test\n"
        "Address for Communication: 12 North Street\n"
        "Caste: SC\n"
    )

    assert fields["Student Name"] == "Nivethitha R"
    assert fields["Father's Name"] == "Ramesh Kumar"
    assert fields["Mother's Name"] == "Sangeetha R"
    assert fields["Date of Birth"] == "30/06/2006"
    assert fields["Gender"] == "F"
    assert fields["Mobile Number"] == "1234567890"
    assert fields["Email"] == "student@example.test"
    assert fields["Address"] == "12 North Street"
    assert fields["Community"] == "SC"
    assert fields["Course Applied"] == ""
    assert quality["review_required"]


def test_ocr_inline_answers_are_mapped_without_accepting_neighboring_text():
    fields, _ = map_fields(
        "GenderM\n"
        "NameN\n"
        "Roll No. OC\n"
        "Nationality INDIAN\n"
        "NationalityINDIAN\n"
        "StudentNameNivethitha\n"
        "Father's / Guardian's Name RAMESHKUMAR.G\n"
        "Mobile No student:6384214363\n"
    )

    assert fields["Gender"] == "M"
    assert fields["Student Name"] == "Nivethitha"
    assert fields["Roll No"] == ""
    assert fields["Nationality"] == "INDIAN"
    assert fields["Father's Name"] == "RAMESHKUMAR.G"
    assert fields["Mobile Number"] == "6384214363"


def test_unlabelled_neighboring_lines_are_never_used_as_answers():
    fields, _ = map_fields("Name\nAsha Raman\nFather Mobile No: 9876543210")

    assert fields["Student Name"] == ""
    assert fields["Mobile Number"] == ""
    assert map_fields("Father's / Guardian's Name DNC")[0]["Father's Name"] == ""


def test_address_label_extension_is_not_mistaken_for_its_value():
    fields, _ = map_fields("Address for Communication")

    assert fields["Address"] == ""


def test_date_validator_accepts_iso_reference_workbook_values():
    assert _valid_value("Date of Birth", "2006-03-02") == "2006-03-02"
    assert (
        _valid_value("Received Date", "2024-01-15 00:00:00")
        == "2024-01-15 00:00:00"
    )
    assert _valid_value("Date of Birth", "31/06/2006") == ""
    assert _valid_value("Date of Birth", "not a date") == ""
    assert map_fields("Date of Birth: 31/06/2006")[0]["Date of Birth"] == ""


def test_academic_percentage_accepts_numeric_reference_values_without_percent():
    assert _valid_value("Academic Percentage", "87.5") == "87.5"
    assert _valid_value("Academic Percentage", "87.5%") == "87.5%"
    assert _valid_value("Academic Percentage", "100") == "100"
    assert _valid_value("Academic Percentage", "100.1%") == ""


def test_checkbox_detector_extracts_only_confident_yes_no_marks():
    image = Image.new("RGB", (982, 1584), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(793, 1292), (798, 1298), (805, 1289)], fill="black", width=2)
    draw.line([(850, 1380), (855, 1386), (860, 1378)], fill="black", width=2)

    assert ocr._checkbox_selections(image) == [
        {
            "checkbox_field": "Physically Challenged",
            "checkbox_value": "yes",
        },
        {
            "checkbox_field": "First Graduate",
            "checkbox_value": "no",
        },
    ]


def test_checkbox_detector_leaves_empty_regions_unselected():
    image = Image.new("RGB", (982, 1584), "white")

    assert ocr._checkbox_selections(image) == []


def test_embedded_layout_fills_only_regions_not_detected_by_ocr():
    merged = ocr._merge_embedded_layout(
        [{"text": "OCR", "bbox": [0, 0, 20, 10]}],
        [
            {"text": "recognized", "bbox": [1, 1, 18, 9]},
            {"text": "supplement", "bbox": [30, 0, 50, 10]},
        ],
        scale_x=0.5,
        scale_y=0.5,
    )

    assert merged == [
        {"text": "OCR", "bbox": [0.0, 0.0, 10.0, 5.0]},
        {"text": "supplement", "bbox": [30.0, 0.0, 50.0, 10.0]},
    ]


def test_perspective_correction_leaves_page_without_clear_corners_unchanged():
    image = Image.new("RGB", (320, 420), "white")

    corrected, applied = ocr._correct_image_perspective(image)

    assert corrected is image
    assert not applied


def test_perspective_correction_rectifies_a_clear_page_quadrilateral():
    canvas = np.full((420, 320, 3), 80, dtype=np.uint8)
    page_corners = np.array([[44, 24], [280, 48], [260, 392], [22, 360]], dtype=np.int32)
    cv2.fillConvexPoly(canvas, page_corners, (245, 245, 245))

    corrected, applied = ocr._correct_image_perspective(Image.fromarray(canvas))

    assert applied
    assert corrected.size != (320, 420)
    assert corrected.width > corrected.height * 0.5


def test_hybrid_pdf_runs_ocr_only_on_pages_with_large_images(tmp_path, monkeypatch):
    path = tmp_path / "hybrid.pdf"
    image_stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image_stream, format="PNG")
    document = fitz.open()
    text_page = document.new_page()
    text_page.insert_text((30, 30), "Name: Student Example")
    scanned_page = document.new_page()
    scanned_page.insert_image(scanned_page.rect, stream=image_stream.getvalue())
    document.save(path)
    document.close()

    calls = []

    def fake_ocr(image, timings=None):
        calls.append(image.size)
        if timings is not None:
            timings.update({
                "model_initialization_ms": 0,
                "ocr_inference_ms": 1,
                "layout_processing_ms": 0,
            })
        return "scanned content", [{"text": "scanned", "bbox": [10, 10, 30, 20]}]

    monkeypatch.setattr(ocr, "ocr_image_layout", fake_ocr)
    timings = {}
    text, method, layout = ocr._extract_with_layout_uncached(path, timings)

    assert method == "paddleocr"
    assert calls == [(1190, 1684)]
    assert "Name:" in text
    assert "scanned content" in text
    assert any(item["text"] == "Student" and item["page_index"] == 0 for item in layout)
    assert timings["ocr_inference_ms"] == 1


def test_trocr_engine_uses_positioned_handwriting_crops(
    tmp_path, monkeypatch
):
    path = tmp_path / "trocr.pdf"
    image_stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image_stream, format="PNG")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((30, 30), "Name")
    page.insert_image(page.rect, stream=image_stream.getvalue())
    document.save(path)
    document.close()

    crop = Image.new("RGB", (60, 20), "white")
    handwriting = types.ModuleType("app.services.handwriting")
    handwriting.recognize_crops = lambda crops, timings=None: ["Student Example"]
    regions = types.ModuleType("app.services.template_regions")
    regions.handwriting_regions = lambda *args: [{
        "field": "Student Name",
        "bbox": [120.0, 25.0, 180.0, 35.0],
        "crop": crop,
    }]
    monkeypatch.setitem(sys.modules, handwriting.__name__, handwriting)
    monkeypatch.setitem(sys.modules, regions.__name__, regions)
    monkeypatch.setenv("OCR_ENGINE", "trocr")

    text, method, layout = ocr._extract_with_layout_uncached(path, {})

    assert method == "trocr"
    assert "Student Example" in text
    assert any(item["text"] == "Student Example" for item in layout)


def test_template_regions_crop_handwriting_after_a_positioned_label():
    image = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(80, 104), (110, 99), (130, 105)], fill="black", width=3)
    layout = [
        {"text": "Name", "bbox": [10, 50, 30, 60], "page_index": 0},
        {"text": "form boundary", "bbox": [185, 100, 199, 110], "page_index": 0},
    ]

    regions = handwriting_regions(
        layout,
        page_index=0,
        page_rect=fitz.Rect(0, 0, 200, 200),
        image=image,
    )

    assert len(regions) == 1
    assert regions[0]["field"] == "Student Name"
    assert regions[0]["crop"].size[0] > 0


def test_template_regions_skip_blank_answer_lines():
    image = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(60, 110), (260, 110)], fill="#555", width=2)
    layout = [
        {"text": "Name", "bbox": [10, 50, 30, 60], "page_index": 0},
        {"text": "form boundary", "bbox": [185, 100, 199, 110], "page_index": 0},
    ]

    assert not handwriting_regions(
        layout,
        page_index=0,
        page_rect=fitz.Rect(0, 0, 200, 200),
        image=image,
    )


def test_positioned_checkbox_selection_overrides_ambiguous_ocr_text():
    fields, _ = map_fields(
        "Physically Challenged: yes",
        [
            {
                "text": "",
                "bbox": None,
                "checkbox_field": "Physically Challenged",
                "checkbox_value": "no",
            }
        ],
    )

    assert fields["Physically Challenged"] == "no"


def test_layout_pairs_answers_to_labels_on_the_same_row():
    layout = [
        {"text": "Name", "bbox": [10, 10, 40, 20]},
        {"text": "Nivethitha R", "bbox": [45, 10, 110, 20]},
        {"text": "Date of Birth", "bbox": [200, 10, 260, 20]},
        {"text": "30/06/2006", "bbox": [265, 10, 320, 20]},
        {"text": "Father's / Guardian's Name", "bbox": [10, 40, 150, 50]},
        {"text": "Ramesh Kumar", "bbox": [155, 40, 220, 50]},
        {"text": "Mother's Name", "bbox": [10, 70, 90, 80]},
        {"text": "Sangeetha R", "bbox": [95, 70, 155, 80]},
        {"text": "Gender", "bbox": [200, 70, 240, 80]},
        {"text": "F", "bbox": [245, 70, 252, 80]},
        {"text": "Mobile No student", "bbox": [10, 100, 95, 110]},
        {"text": "1234567890", "bbox": [100, 100, 150, 110]},
        {"text": "Email ID Student", "bbox": [200, 100, 280, 110]},
        {"text": "student@example.test", "bbox": [285, 100, 390, 110]},
        {"text": "Address for Communication", "bbox": [10, 130, 140, 140]},
        {"text": "12 North Street", "bbox": [145, 130, 230, 140]},
        {"text": "Caste", "bbox": [250, 130, 280, 140]},
        {"text": "SC", "bbox": [285, 130, 300, 140]},
    ]

    fields, _ = map_fields("", layout)

    assert {key: fields[key] for key in (
        "Student Name",
        "Date of Birth",
        "Gender",
        "Father's Name",
        "Mother's Name",
        "Mobile Number",
        "Email",
        "Address",
        "Community",
        "Course Applied",
    )} == {
        "Student Name": "Nivethitha R",
        "Date of Birth": "30/06/2006",
        "Gender": "F",
        "Father's Name": "Ramesh Kumar",
        "Mother's Name": "Sangeetha R",
        "Mobile Number": "1234567890",
        "Email": "student@example.test",
        "Address": "12 North Street",
        "Community": "SC",
        "Course Applied": "",
    }


def test_layout_collects_multiline_address_only_until_next_label_in_its_column():
    layout = [
        {"text": "Address for Communication", "bbox": [10, 10, 150, 20]},
        {"text": "3-166, North Street", "bbox": [10, 24, 125, 32]},
        {"text": "Paliyapuram", "bbox": [10, 36, 78, 44]},
        {"text": "Bank Name", "bbox": [250, 24, 310, 32]},
        {"text": "Bank of Baroda", "bbox": [315, 24, 390, 32]},
        {"text": "Father Mobile No", "bbox": [10, 52, 100, 60]},
        {"text": "9876543210", "bbox": [105, 52, 160, 60]},
    ]

    fields, _ = map_fields("", layout)

    assert fields["Address"] == "3-166, North Street Paliyapuram"
    assert fields["Bank Name"] == "Bank of Baroda"
    assert fields["Father Mobile No"] == "9876543210"


def test_academic_headings_are_not_mapped_as_values():
    fields, _ = map_fields(
        "",
        [
            {"text": "Percentage", "bbox": [10, 10, 90, 20]},
            {"text": "677 66%", "bbox": [95, 10, 145, 20]},
            {"text": "Last Studied Institution", "bbox": [10, 40, 150, 50]},
            {"text": "Subjects", "bbox": [155, 40, 215, 50]},
        ],
    )

    assert fields["Academic Percentage"] == ""
    assert fields["Last Studied Institution with Address"] == ""


def test_academic_records_keep_columns_separated_for_manual_review():
    layout = [
        {"text": "Last Studied", "bbox": [10, 10, 65, 20]},
        {"text": "Institution", "bbox": [70, 10, 125, 20]},
        {"text": "Subjects", "bbox": [10, 40, 70, 50]},
        {"text": "Register No", "bbox": [150, 40, 220, 50]},
        {"text": "Maximum Mark", "bbox": [300, 40, 390, 50]},
        {"text": "Marks Obtained", "bbox": [470, 40, 560, 50]},
        {"text": "Mathematics", "bbox": [10, 60, 90, 70]},
        {"text": "12345", "bbox": [150, 60, 190, 70]},
        {"text": "100", "bbox": [300, 60, 325, 70]},
        {"text": "88", "bbox": [470, 60, 485, 70]},
        {"text": "Rules and Regulations", "bbox": [10, 100, 140, 110]},
    ]

    fields, _ = map_fields("", layout)

    records = fields["XI & XII Academic Records"]
    assert "Subjects\tRegister No\tMaximum Mark\tMarks Obtained" in records
    assert "Mathematics\t12345\t100\t88" in records


def test_parent_name_label_does_not_become_student_name():
    fields, _ = map_fields(
        "",
        [
            {"text": "Father's Name", "bbox": [10, 10, 100, 20]},
            {"text": "Ramesh", "bbox": [105, 10, 140, 20]},
        ],
    )

    assert fields["Student Name"] == ""
    assert fields["Father's Name"] == "Ramesh"


def test_positioned_value_overrides_misassociated_flat_text():
    fields, _ = map_fields(
        "Father's / Guardian's Name DNC",
        [
            {"text": "Father's / Guardian's Name", "bbox": [10, 10, 150, 20]},
            {"text": "Ramesh Kumar", "bbox": [155, 10, 230, 20]},
            {"text": "DNC", "bbox": [400, 10, 430, 20]},
        ],
    )

    assert fields["Father's Name"] == "Ramesh Kumar"


def test_positioned_name_values_use_page_geometry_not_rightmost_text_extent():
    layout = [
        {"text": "Student", "bbox": [50, 60, 91, 76], "page_index": 0, "page_width": 595},
        {"text": "Name:", "bbox": [95, 60, 130, 76], "page_index": 0, "page_width": 595},
        {"text": "Synthetic", "bbox": [133, 60, 183, 76], "page_index": 0, "page_width": 595},
        {"text": "Test", "bbox": [186, 60, 209, 76], "page_index": 0, "page_width": 595},
        {"text": "Applicant", "bbox": [212, 60, 262, 76], "page_index": 0, "page_width": 595},
        {"text": "Father's", "bbox": [50, 90, 93, 106], "page_index": 0, "page_width": 595},
        {"text": "Name:", "bbox": [96, 90, 132, 106], "page_index": 0, "page_width": 595},
        {"text": "Synthetic", "bbox": [135, 90, 184, 106], "page_index": 0, "page_width": 595},
        {"text": "Test", "bbox": [187, 90, 211, 106], "page_index": 0, "page_width": 595},
        {"text": "Guardian", "bbox": [214, 90, 266, 106], "page_index": 0, "page_width": 595},
    ]

    fields, _ = map_fields("", layout)

    assert fields["Student Name"] == "Synthetic Test Applicant"
    assert fields["Father's Name"] == "Synthetic Test Guardian"


def test_supplied_scan_never_maps_neighboring_printed_labels_as_answers():
    sample = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "documents"
        / "BFS26002.pdf"
    )
    assert sample.is_file()

    fields, quality = map_fields(pdf_text(sample), pdf_layout(sample))

    assert fields["Student Name"] != "Nationality TNDIAN"
    assert fields["Father's Name"] != "DNC"
    assert fields["Mother's Name"] != "SC"
    assert "Aadhaar" not in fields["Address"]
    assert fields["Community"] != "PARALYAN"
    assert quality["review_required"]


def test_hybrid_sample_with_text_layer_still_requires_ocr():
    sample = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "documents"
        / "BFS26002.pdf"
    )

    assert pdf_text(sample)
    assert ocr._needs_ocr(sample)


def test_extraction_cache_reports_timings_and_avoids_reprocessing(
    tmp_path, monkeypatch
):
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"sample")
    calls = []

    def fake_extract(path, timings):
        calls.append(path)
        timings.update({
            "ocr_detection_ms": 4,
            "pdf_render_ms": 10,
            "ocr_inference_ms": 25,
            "layout_processing_ms": 2,
            "checkbox_detection_ms": 6,
            "model_initialization_ms": 100,
        })
        return "recognized text", "paddleocr", [{"text": "Name"}]

    monkeypatch.setattr(ocr, "_extract_with_layout_uncached", fake_extract)
    ocr._cached_extract.cache_clear()
    try:
        first_timings = {}
        first_result = ocr.extract_with_layout(sample, first_timings)
        second_timings = {}
        second_result = ocr.extract_with_layout(sample, second_timings)
    finally:
        ocr._cached_extract.cache_clear()

    assert first_result == second_result
    assert len(calls) == 1
    assert first_timings["cache_hit"] is False
    assert first_timings["model_initialization_ms"] == 100
    assert first_timings["ocr_inference_ms"] == 25
    assert first_timings["total_extraction_ms"] >= 0
    assert second_timings["cache_hit"] is True
    assert second_timings["ocr_inference_ms"] == 0
    assert second_timings["pdf_render_ms"] == 0
    assert second_timings["checkbox_detection_ms"] == 0


def test_concurrent_requests_for_one_document_share_extraction(
    tmp_path, monkeypatch
):
    sample = tmp_path / "same.pdf"
    sample.write_bytes(b"sample")
    calls = []

    def fake_extract(path, timings):
        calls.append(path)
        sleep(0.05)
        timings.update({"ocr_inference_ms": 25})
        return "recognized text", "paddleocr", []

    monkeypatch.setattr(ocr, "_extract_with_layout_uncached", fake_extract)
    ocr._cached_extract.cache_clear()
    try:
        def extract_once():
            timings = {}
            result = ocr.extract_with_layout(sample, timings)
            return result, timings

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(extract_once) for _ in range(2)]
            results = [future.result() for future in futures]
    finally:
        ocr._cached_extract.cache_clear()

    assert len(calls) == 1
    assert results[0][0] == results[1][0]
    assert sorted(result[1]["cache_hit"] for result in results) == [False, True]
