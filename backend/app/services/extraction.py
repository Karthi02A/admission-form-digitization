
import re
from rapidfuzz import fuzz, process
from datetime import datetime

from app.config.settings import ALIASES, CHECKBOX_FIELDS, COURSE_OPTIONS


BOUNDARY_LABELS = [
    "nationality", "religion", "caste", "sub caste", "aadhaar no", "pan no",
    "bank name", "bank a c no", "ifsc code", "blood group",
    "father mobile no", "tel no", "pin", "emis no",
    "identification mark 1", "identification mark 2",
    "physically challenged", "enclosed certificate", "parents occupation",
    "income", "first graduate", "admission no", "received by",
    "received date", "last studied institution",
]


def clean(value: str) -> str:
    """Normalize whitespace and remove surrounding separators."""
    value = re.sub(r"\s+", " ", str(value or ""))
    return value.strip(" \t:;|-_.,")


def normalize_label(value: str) -> str:
    """Normalize a label for tolerant matching."""
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _aliases():
    """Return normalized aliases, preferring longer and more specific labels."""
    return sorted(
        (
            (field, normalize_label(alias))
            for field, aliases in ALIASES.items()
            for alias in aliases
            if normalize_label(alias)
        ),
        key=lambda item: len(item[1].split()),
        reverse=True,
    )


def _label_pattern(alias: str) -> str:
    words = normalize_label(alias).split()
    return r"[\s:/|.'_-]+".join(re.escape(word) for word in words)


def _inline_value(line, aliases, separator_only=False):
    """Find a field and its value on one OCR text line."""
    for field, alias in aliases:
        separator = (
            r"\s*[:=]\s*"
            if separator_only
            else r"(?:\s*[:=\-\u2013\u2014]\s*|\s+)"
        )
        pattern = (
            r"^\s*" + _label_pattern(alias)
            + r"(?:" + separator + r")(.+?)\s*$"
        )
        match = re.match(pattern, line, re.IGNORECASE)
        if not match:
            continue

        value = clean(match.group(1))
        normalized_value = normalize_label(value)

        if alias == "address" and normalized_value.startswith("for communication"):
            continue

        normalized_compact = normalized_value.replace(" ", "")
        contains_label = any(
            len(other.split()) > 1
            and (
                f" {other} " in f" {normalized_value} "
                or other.replace(" ", "") in normalized_compact
            )
            for _, other in aliases
            if other != alias
        )
        if contains_label:
            continue

        if value and not any(
            re.fullmatch(_label_pattern(other), value, re.IGNORECASE)
            for _, other in aliases
        ):
            return field, value

    return None, ""


def _layout_rows(layout):
    """Group OCR layout tokens into approximate visual rows."""
    tokens = []
    page_widths = {}

    for item in layout or []:
        text = clean(str(item.get("text", "")))
        box = item.get("bbox")

        if not text or not isinstance(box, (list, tuple)) or len(box) < 4:
            continue

        try:
            x0, y0, x1, y1 = (float(value) for value in box[:4])
            page_index = int(item.get("page_index", 0))
        except (TypeError, ValueError):
            continue

        tokens.append({
            "text": text,
            "page_index": page_index,
            "x0": min(x0, x1),
            "y0": min(y0, y1),
            "x1": max(x0, x1),
            "y1": max(y0, y1),
        })
        try:
            page_width = float(item.get("page_width", 0))
        except (TypeError, ValueError):
            page_width = 0
        page_widths[page_index] = max(
            page_widths.get(page_index, 0),
            page_width,
            max(x0, x1),
        )

    tokens.sort(key=lambda token: (
        token["page_index"],
        (token["y0"] + token["y1"]) / 2,
        token["x0"],
    ))

    rows = []
    for token in tokens:
        center = (token["y0"] + token["y1"]) / 2
        token_height = token["y1"] - token["y0"]

        row = next(
            (
                candidate for candidate in reversed(rows)
                if candidate["page_index"] == token["page_index"]
                and abs(candidate["center"] - center) <= max(
                    4.0,
                    min(token_height, candidate["height"]) * 0.65,
                )
            ),
            None,
        )

        if row is None:
            rows.append({
                "center": center,
                "height": token_height,
                "page_index": token["page_index"],
                "page_width": page_widths.get(token["page_index"], 0),
                "tokens": [token],
            })
        else:
            row["tokens"].append(token)
            row["center"] = sum(
                (item["y0"] + item["y1"]) / 2
                for item in row["tokens"]
            ) / len(row["tokens"])
            row["height"] = max(row["height"], token_height)

    for row in rows:
        row["tokens"].sort(key=lambda token: token["x0"])

    return rows


def _find_row_labels(row, aliases):
    """Find known field labels in a row of positioned OCR tokens."""
    words = []

    for index, token in enumerate(row["tokens"]):
        for word in normalize_label(token["text"]).split():
            words.append((word, index))

    found = []
    mapped_aliases = {alias for _, alias in aliases}
    all_aliases = aliases + [
        (None, normalize_label(alias))
        for alias in BOUNDARY_LABELS
        if normalize_label(alias) not in mapped_aliases
    ]

    for field, alias in all_aliases:
        expected = alias.split()
        if not expected:
            continue

        for start in range(len(words) - len(expected) + 1):
            if [item[0] for item in words[start:start + len(expected)]] != expected:
                continue

            preceding = {
                word for word, _ in words[max(0, start - 4):start]
            }

            if alias == "name" and (
                start != 0
                or preceding.intersection({
                    "father", "mother", "guardian", "declaration", "declare",
                })
            ):
                continue

            if alias == "address" and start != 0:
                continue

            if alias == "caste" and "sub" in preceding:
                continue

            first_token = words[start][1]
            last_token = words[start + len(expected) - 1][1]

            found.append({
                "field": field,
                "first": first_token,
                "last": last_token,
                "x": row["tokens"][last_token]["x1"],
                "start_x": row["tokens"][first_token]["x0"],
                "length": len(expected),
            })

    # Existing exact‑match processing
    unique = {}
    for label in found:
        key = (label["first"], label["field"])
        current = unique.get(key)
        if current is None or label["length"] > current["length"]:
            unique[key] = label
    labels = list(unique.values())
    labels = [
        label for label in labels
        if not any(
            other["first"] == label["first"]
            and other["last"] >= label["last"]
            and other["length"] > label["length"]
            for other in labels
        )
    ]
    # Fuzzy‑match fallback: if no exact label was found for a field, try a fuzzy match on the whole row text.
    if not labels:
        row_text = " ".join(token["text"] for token in row["tokens"]).lower()
        for field, alias in aliases:
            # Compute fuzzy ratio between alias and row text
            if fuzz.partial_ratio(alias.lower(), row_text) >= 85:
                # Approximate position: use first token as start, last token as end
                label = {
                    "field": field,
                    "first": 0,
                    "last": len(row["tokens"]) - 1,
                    "x": row["tokens"][-1]["x1"],
                    "start_x": row["tokens"][0]["x0"],
                    "length": len(alias.split()),
                }
                labels.append(label)
                break
    return sorted(labels, key=lambda label: (label["first"], -label["length"]))


def _valid_value(field, value):
    """Reject obvious label contamination and invalid field formats."""
    value = clean(value)
    if not value:
        return ""

    if field in {
        "Received By", "Student Name", "Father's Name", "Mother's Name",
    }:
        if normalize_label(value).upper() in {
            "OC", "BC", "MBC", "DNC", "SC", "ST", "M", "F",
        }:
            return ""
        return value if re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]{2,79}", value
        ) else ""

    if field == "Nationality":
        return value if re.fullmatch(r"[A-Za-z][A-Za-z -]{1,39}", value) else ""

    if field == "Religion":
        return value if re.fullmatch(r"[A-Za-z][A-Za-z -]{1,39}", value) else ""

    if field == "Bank Name":
        return value if re.fullmatch(r"[A-Za-z][A-Za-z .&'-]{2,79}", value) else ""

    if "Date" in field:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            for date_format in (
                "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y",
                "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y",
            ):
                try:
                    datetime.strptime(value, date_format)
                    return value
                except ValueError:
                    continue
            return ""

    if field == "Gender":
        if re.fullmatch(r"(?:m|f|male|female)", value, re.IGNORECASE):
            return value.upper() if value.casefold() in {"m", "f"} else value
        return ""

    if field in {"Physically Challenged", "First Graduate"}:
        return value if value.casefold() in {"yes", "no"} else ""

    if field == "Community":
        return value if re.fullmatch(
            r"(?:OC|BC|MBC|DNC|BC\(M\)|BC\(C\)|SC|ST)",
            value,
            re.IGNORECASE,
        ) else ""

    if field == "Course Applied":
        options = {normalize_label(option) for option in COURSE_OPTIONS}
        normalized = normalize_label(value)
        return value if normalized in options else ""

    if field in CHECKBOX_FIELDS:
        return value if value.casefold() in {
            "yes", "no", "attached", "enclosed", "submitted",
        } else ""

    if field in {"Father Mobile No", "Mobile Number", "Telephone No"}:
        digits = re.sub(r"[\s()+.-]", "", value)
        return value if re.fullmatch(r"\d{6,15}", digits) else ""

    if field == "Email":
        return value if re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            value,
        ) else ""

    if field == "Address":
        if re.search(
            r"\b(?:aadhaar|pan|bank|ifsc|email|mobile|pin|communication)\b",
            value,
            re.IGNORECASE,
        ):
            return ""
        return value if re.fullmatch(r"[A-Za-z0-9 ,./#'()\-]{8,}", value) else ""

    if field in {
        "Aadhaar No", "Pan No", "Bank A/C No", "IFSC Code", "Pincode",
        "EMIS No", "Roll No", "Application No", "Admission No",
        "XI Standard Register No", "XII Standard Register No",
    }:
        digits = re.sub(r"\s", "", value)

        if field == "Roll No" and not re.search(r"\d", value):
            return ""
        if field == "Pincode" and not re.fullmatch(r"\d{6}", digits):
            return ""
        if field == "Aadhaar No" and not re.fullmatch(r"\d{12}", digits):
            return ""
        if field == "Bank A/C No" and not re.fullmatch(r"\d{6,20}", digits):
            return ""
        if field == "IFSC Code" and not re.fullmatch(
            r"[A-Za-z]{4}0[A-Za-z0-9]{6}", value.replace(" ", "")
        ):
            return ""

        return value if re.fullmatch(r"[A-Za-z0-9 /-]{2,32}", value) else ""

    if field in {
        "Admission Fee", "Income", "Academic Total Marks",
        "XI Standard Marks Obtained", "XII Standard Marks Obtained",
        "XI Standard Total Marks", "XII Standard Total Marks",
    }:
        return value if re.fullmatch(r"[0-9,.% /-]{1,40}", value) else ""

    if field == "Academic Percentage":
        if not re.fullmatch(
            r"(?:100(?:\.0+)?|[0-9]{1,2}(?:\.[0-9]+)?)\s*%?",
            value,
        ):
            return ""
        return value if float(value.rstrip("%").strip()) <= 100 else ""

    if field in {"Parent / Guardian Signature", "Applicant Signature"}:
        return ""

    if field == "Last Studied Institution with Address" and normalize_label(value) in {
        "subjects", "reg no", "maximum mark", "marks obtained", "marks",
        "institution",
    }:
        return ""

    return value


def _fused_inline_value(line, aliases):
    """Read a value attached to a label only if validation accepts it."""
    fused_fields = {
        "Received By", "Student Name", "Father's Name", "Mother's Name",
        "Nationality", "Religion", "Bank Name", "Gender", "Community",
        "Physically Challenged", "First Graduate", "Transfer Certificate",
        "Mark Sheets", "Community Certificate", "Income Certificate",
        "Father Mobile No", "Telephone No", "Mobile Number", "Pincode",
        "Aadhaar No", "Bank A/C No", "IFSC Code", "EMIS No", "Roll No",
        "Application No", "Admission No", "Date of Birth", "Received Date",
        "Admission Date", "Email",
    }

    for field, alias in aliases:
        if field not in fused_fields:
            continue

        pattern = (
            r"^\s*" + r"[\s:/|.'_-]*".join(
                re.escape(word) for word in alias.split()
            ) + r"(.*)$"
        )
        match = re.match(pattern, line, re.IGNORECASE)
        if not match:
            continue

        suffix = clean(match.group(1))
        if field in {
            "Received By", "Student Name", "Father's Name", "Mother's Name",
            "Nationality", "Religion", "Bank Name",
        } and len(suffix) < 3:
            continue

        if suffix:
            value = _valid_value(field, suffix)
            if value:
                if field == "Gender":
                    value = value.upper() if value.casefold() in {"m", "f"} else value
                elif field == "Community":
                    value = value.upper()
                return field, value

    return None, ""


def _academic_records(rows):
    """Collect OCR rows covering the academic-record section."""
    start = None
    end = None

    for index, row in enumerate(rows):
        text = normalize_label(
            " ".join(token["text"] for token in row["tokens"])
        )

        if start is None and "last studied institution" in text:
            start = index
            continue

        if start is not None and "rules and regulations" in text:
            end = index
            break

    if start is None:
        return ""

    selected = rows[start:end]
    formatted_rows = []
    for row in selected:
        tokens = [token for token in row["tokens"] if token["text"].strip()]
        if not tokens:
            continue
        parts = [tokens[0]["text"]]
        for previous, token in zip(tokens, tokens[1:]):
            separator = "\t" if token["x0"] - previous["x1"] >= row["page_width"] * 0.035 else " "
            parts.append(separator + token["text"])
        formatted_rows.append("".join(parts).strip())
    return "\n".join(formatted_rows)


def map_fields(text: str, layout=None):
    """
    Map OCR output to the fixed admission-form fields.

    Positioned values are preferred. Inline parsing is used as a fallback.
    Missing values remain blank rather than being guessed.
    """
    output = {field: "" for field in ALIASES}
    aliases = _aliases()

    checkbox_values = {
        item["checkbox_field"]: item["checkbox_value"]
        for item in (layout or [])
        if item.get("checkbox_field") in {
            "Physically Challenged", "First Graduate",
        }
        and item.get("checkbox_value") in {"yes", "no"}
    }

    lines = [clean(line) for line in (text or "").splitlines()]
    rows = _layout_rows(layout)

    located_labels = [
        (row, label)
        for row in rows
        for label in _find_row_labels(row, aliases)
        if label["field"] is not None
    ]

    # 1. Map values appearing to the right of labels on the same visual row.
    for row in rows:
        labels = _find_row_labels(row, aliases)

        for position, label in enumerate(labels):
            field = label["field"]
            if field is None:
                continue

            stop_x = (
                labels[position + 1]["start_x"]
                if position + 1 < len(labels)
                else float("inf")
            )

            max_ratio = {
                "Student Name": 0.68,
                "Father's Name": 0.55,
                "Mother's Name": 0.55,
                "Address": 0.46,
            }.get(field)

            if max_ratio and row["page_width"] * max_ratio > label["x"]:
                stop_x = min(stop_x, row["page_width"] * max_ratio)

            value = " ".join(
                token["text"]
                for token in row["tokens"]
                if token["x0"] >= label["x"]
                and token["x0"] < stop_x
            ).strip()

            value = _valid_value(field, value)
            if value and not output[field]:
                output[field] = value

    # 2. Recover a multi-line address, stopping before the next field label.
    if not output["Address"]:
        for row, label in located_labels:
            if label["field"] != "Address":
                continue

            next_label_y = min(
                (
                    candidate_row["center"]
                    for candidate_row, candidate in located_labels
                    if candidate_row["page_index"] == row["page_index"]
                    and candidate_row["center"] > row["center"]
                    and abs(candidate["start_x"] - label["start_x"])
                    <= row["page_width"] * 0.08
                ),
                default=row["center"] + row["page_width"] * 0.14,
            )

            address_lines = []
            for candidate_row in rows:
                if (
                    candidate_row["page_index"] != row["page_index"]
                    or not row["center"] < candidate_row["center"] < next_label_y
                ):
                    continue

                value = " ".join(
                    token["text"]
                    for token in candidate_row["tokens"]
                    if token["x0"] >= label["start_x"] - row["page_width"] * 0.015
                    and token["x0"] < row["page_width"] * 0.46
                )

                value = _valid_value("Address", value)
                if value:
                    address_lines.append(value)

            output["Address"] = _valid_value(
                "Address", " ".join(address_lines)
            )
            break

    # 3. Keep the academic table text in its dedicated field.
    if layout and "XI & XII Academic Records" in output:
        output["XI & XII Academic Records"] = _academic_records(rows)

    # 4. Use inline and fused-label parsing only when a field is still empty.
    for line in lines:
        if not line:
            continue

        field, value = _inline_value(line, aliases)

        if field:
            if not output[field]:
                value = _valid_value(field, value)
                if value:
                    output[field] = value
            continue

        field, value = _fused_inline_value(line, aliases)
        if field and not output[field]:
            value = _valid_value(field, value)
            if value:
                output[field] = value

    # 5. Explicit checkbox detections override text guesses for these fields.
    for field, value in checkbox_values.items():
        output[field] = _valid_value(field, value)

    missing = [field for field, value in output.items() if not value]
    quality = {
        "total_fields": len(output),
        "filled_fields": len(output) - len(missing),
        "missing_fields": missing,
        "review_required": bool(missing),
    }

    return output, quality


# ---------------------------------------------------------------------------
# Direct vision-model extraction: original PDF/image -> canonical fields.
# This is the live extraction path. It does not run local OCR or a second
# text-to-field mapping pass.
# ---------------------------------------------------------------------------
import base64 as _base64
import json as _json
import mimetypes as _mimetypes
import os as _os
import time as _time
from pathlib import Path as _Path
from typing import Any as _Any
from dotenv import load_dotenv as _load_dotenv
# Support backend/.env and project-root .env; process environment takes precedence.
_backend_env = _Path(__file__).resolve().parents[2] / ".env"
_project_env = _Path(__file__).resolve().parents[3] / ".env"
_load_dotenv(_backend_env)
if _project_env != _backend_env:
    _load_dotenv(_project_env)

import httpx as _httpx
import pymupdf as _fitz
from app.config.ai_settings import load_ai_settings as _load_ai_settings
from app.config.settings import MAX_PAGES as _MAX_PAGES


def _document_input(file_path: str | _Path) -> tuple[str, str, int]:
    """Return original document bytes encoded for Gemini; never OCR/render it locally."""
    path = _Path(file_path)
    if not path.is_file():
        raise FileNotFoundError("Original document file was not found.")
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            with _fitz.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                page_count = len(pdf)
                if page_count < 1:
                    raise ValueError("The PDF contains no pages.")
                if page_count > _MAX_PAGES:
                    raise ValueError(f"PDF has {page_count} pages; configured limit is {_MAX_PAGES}.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The uploaded PDF could not be opened.") from exc
        mime = "application/pdf"
    elif ext in {".jpg", ".jpeg", ".png"}:
        mime = "image/png" if ext == ".png" else "image/jpeg"
        page_count = 1
    else:
        raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted.")
    raw = path.read_bytes()
    if not raw:
        raise ValueError("The document file is empty.")
    return _base64.b64encode(raw).decode("ascii"), mime, page_count


def _vision_prompt() -> str:
    # Compact JSON reduces prompt overhead while keeping the fixed template schema explicit.
    schema = {field: "string" for field in ALIASES}
    compact = lambda value: _json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    checkbox_fields = sorted(set(CHECKBOX_FIELDS) | {"Course Applied"})
    return f"""You extract data from the supplied college admission application. Read the ORIGINAL attached PDF/image directly. Inspect every page and map only visible answers to the fixed schema. Do not rely on an OCR transcript. The field schema describes the expected form; it is not evidence that a field has a value.

Return exactly one JSON object: {{"fields":{{...}}}}. Include every canonical key below, no other keys, and make every value a string.
For ordinary fields, use "-" only when the corresponding area on the original form is visibly blank or the information is clearly not provided. Use "" when the information appears to be present but is unreadable, ambiguous, or cannot be mapped. For selectable fields ({compact(checkbox_fields)}), use "-" only when the form clearly shows no option selected or the status is clearly not provided; use "" when a mark is present but its meaning is ambiguous or unreadable. Never convert uncertainty into "Yes" or "No".

CANONICAL FIELDS: {compact(schema)}
FIELD LABEL ALIASES: {compact(ALIASES)}
ALLOWED COURSE OPTIONS: {compact(COURSE_OPTIONS)}

RULES:
- Read this student's document independently. Never reuse values from another document or assume a value based on the template.
- First inspect the page layout visually, then read each handwritten answer from the box or line belonging to its printed label. Follow the label-to-value relationship, not text proximity alone. Keep student, parent, guardian, contact, address, and academic fields separate.
- Copy visible handwriting faithfully. Preserve identifiers and numbers as strings, including leading zeroes. Do not silently correct handwriting, spelling, dates, or identifiers. If the field area is visibly empty, return "-". If handwriting or a mark is present but cannot be read or mapped reliably, return "" so the UI marks it for review. Do not guess uncertain characters.
- For every checkbox/radio group, inspect the individual printed boxes and the mark inside each box. Do not infer a selection from nearby handwriting, a field label, or a mark belonging to another row. Return the value associated with the visibly ticked/crossed box only. If no box is marked, use "-"; if the mark or the selected option is ambiguous, use "". Gender, Community, Physically Challenged, First Graduate, and Course Applied must each be read from their own group. Never assume that a printed option is selected just because it appears in the form.
- For Course Applied, inspect every course option box in section (a), including the left, middle, and right columns. Record every clearly ticked course and no unticked course. Map each tick to the exact nearest printed course label in that same row. Return the exact allowed course name(s), joined with "; ". Do not return a guess based on the student's name, photo, course popularity, or another form. Use "-" only if no course is marked. If a course tick is visible but cannot be mapped to a label, return "" for review. If a tick is visible but its label is not confidently identifiable, return the closest visible label text rather than silently omitting it, so the result can be reviewed.
- Keep "Community" and "Sub Caste" distinct: "Community" is the selected printed category (OC, BC, MBC, DNC, BC(M), BC(C), SC, ST, or another visibly printed option); "Sub Caste" is the separately handwritten subgroup text. Never put the handwritten sub-caste name in "Community". If the selected category cannot be read, use "".
- For academic records, read page 2's table by both row and column. Put the complete visible XI-side academic details in "XI Academic Records" and the complete visible XII-side academic details in "XII Academic Records"; preserve subject names and each subject's marks in the appropriate side. Populate the separate XI/XII register-number, marks-obtained, total-marks, maximum-marks, and percentage fields only when those values are visibly present and can be assigned to the correct standard. Never swap XI and XII columns, combine both standards into one field, or infer blank register numbers, totals, or percentages.
- For Transfer Certificate, Mark Sheets, Community Certificate, Income Certificate, Passport-size Photo (4), Aadhaar (Proof), PAN (Proof), and Bank Passbook (Proof), inspect only the corresponding row in the Certificate Details area. The printed list alone is not evidence that a certificate was received. Return "Yes" only when that row contains an unambiguous receipt mark or explicit receipt text. Return "-" only when the row clearly indicates not received/not enclosed or there is clearly no receipt mark in the row; return "" when a mark exists but its status cannot be determined. Do not infer status from unrelated marks, the Remarks column, or office-use marks, and do not assign one row's status to another certificate.
- Do not create extra fields, including an "Enclosed Certificate" field.
- Normalize valid dates to DD/MM/YYYY only when day, month, and year are unambiguous. If ambiguous, preserve the visible date string for review rather than guessing.
- For Income, remove spaces used as thousands separators (for example, "12 000" becomes "12000") but do not change any digits. Preserve identifiers as strings, including leading zeroes; whitespace inside numeric identifiers may be removed only when it is clearly a formatting separator.
- For Blood Group, return only one of A+, A-, B+, B-, AB+, AB-, O+, O-. If the handwriting is not clearly one of these, return "" rather than guessing or converting a variant such as A1+.
- Extract actual entries in office-use sections when present; do not copy printed examples, instructions, or labels as answers.
- Do not calculate missing totals, percentages, ages, or dates. Do not describe signatures; return "" for signature fields unless the schema explicitly requires visible text.
- Return JSON only. No markdown, commentary, confidence score, page number, or extra metadata.
"""



def _normalize_date(value: str) -> str:
    """Normalize only unambiguous dates to DD/MM/YYYY; otherwise preserve input."""
    value = clean(value)
    if not value:
        return ""
    # ISO dates are unambiguous.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    # Accept common separators including spaces. If both first components are
    # <= 12, the order is ambiguous, so preserve the source value for review.
    match = re.fullmatch(r"(\d{1,2})[\s./-]+(\d{1,2})[\s./-]+(\d{2,4})", value)
    if not match:
        return value
    first, second, year = match.groups()
    a, b = int(first), int(second)
    if a <= 12 and b <= 12:
        return value
    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        # Clearly month/day/year; normalize to day/month/year.
        month, day = a, b
    else:
        return value
    year_num = int(year)
    if year_num < 100:
        year_num += 2000 if year_num <= 49 else 1900
    try:
        return datetime(year_num, month, day).strftime("%d/%m/%Y")
    except ValueError:
        return value


def _normalize_course_selection(value: str) -> str:
    """Canonicalize course names without silently dropping an unmatched answer.

    The prompt asks Gemini to use exact course labels. We accept exact normalized
    matches and semicolon/newline-separated multi-selects. If the response still
    cannot be mapped safely, preserve it verbatim for the reviewer instead of
    replacing it with "-". Commas are deliberately not separators because course
    labels themselves contain commas (for example, "B.A., English").
    """
    raw = clean(value)
    if not raw or raw == "-":
        return "-"

    options = {normalize_label(option): option for option in COURSE_OPTIONS}
    exact = options.get(normalize_label(raw))
    if exact:
        return exact

    pieces = [piece.strip() for piece in re.split(r"[;\n]+", raw) if piece.strip()]
    selected: list[str] = []
    unmatched: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        match = options.get(normalize_label(piece))
        if match:
            if match not in seen:
                selected.append(match)
                seen.add(match)
        else:
            unmatched.append(piece)

    # Only return canonical selections if every piece was mapped. Otherwise
    # preserve the original response so the UI can show it for human review.
    if not unmatched and selected:
        return "; ".join(selected)
    return raw


def _normalize_fields(fields: dict[str, str]) -> dict[str, str]:
    """Apply deterministic, provider-independent normalization after AI extraction."""
    normalized = dict(fields)

    # Dates: normalize only if safe; don't infer ambiguous date order.
    for key in ("Date of Birth", "Received Date", "Admission Date"):
        if key in normalized and normalized[key]:
            normalized[key] = _normalize_date(normalized[key])

    # Income is an amount, not an identifier: spaces are thousands separators here.
    if normalized.get("Income"):
        normalized["Income"] = re.sub(r"(?<=\d)\s+(?=\d)", "", normalized["Income"].strip())

    # Numeric summary fields may contain grouping spaces, but retain punctuation/percent.
    for key in (
        "Admission Fee", "Academic Total Marks",
        "XI Standard Marks Obtained", "XII Standard Marks Obtained",
        "XI Standard Total Marks", "XII Standard Total Marks",
        "XI Standard Maximum Marks", "XII Standard Maximum Marks",
        "XI Standard Percentage", "XII Standard Percentage",
        "Academic Percentage",
    ):
        if normalized.get(key):
            normalized[key] = re.sub(r"(?<=\d)\s+(?=\d)", "", normalized[key].strip())

    # Blood group must be one of the eight standard ABO/Rh forms.
    if "Blood Group" in normalized and normalized["Blood Group"]:
        value = re.sub(r"\s+", "", normalized["Blood Group"]).upper()
        normalized["Blood Group"] = value if value in {
            "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"
        } else ""

    # Certificate checkbox policy: Yes only when the model explicitly reports
    # a visible tick. Do not accept words such as "attached" as proof of a tick.
    for key in ("Transfer Certificate", "Mark Sheets", "Community Certificate", "Income Certificate", "Passport-size Photo", "Aadhaar Proof", "PAN Proof", "Bank Passbook Proof"):
        if key in normalized:
            value = normalized[key].strip().casefold()
            if value in {"yes", "checked", "selected", "received"}:
                normalized[key] = "Yes"
            elif value in {"no", "not received", "not enclosed", "unselected", "-"}:
                normalized[key] = "-"
            else:
                normalized[key] = ""

    # Canonicalize simple binary selections without inventing an answer.
    for key in ("Physically Challenged", "First Graduate"):
        if key in normalized:
            value = normalized[key].strip().casefold()
            normalized[key] = "Yes" if value in {"yes", "checked", "selected"} else ("No" if value in {"no", "not checked", "unselected"} else ("-" if value == "-" else ""))

    if normalized.get("Gender"):
        gender = normalized["Gender"].strip().casefold()
        if gender in {"m", "male"}:
            normalized["Gender"] = "Male"
        elif gender in {"f", "female"}:
            normalized["Gender"] = "Female"

    # Course list normalization: commas are part of valid labels such as
    # "B.A., English" and must never be treated as multi-select separators.
    # The helper preserves an unmatched model response for human review instead
    # of silently converting a possibly valid course to "-".
    course = normalized.get("Course Applied", "")
    if course:
        normalized["Course Applied"] = _normalize_course_selection(course)

    return normalized


def _parse_gemini_response(data: dict[str, _Any]) -> dict[str, str]:
    try:
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        content = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    except (KeyError, IndexError, TypeError) as exc:
        feedback = data.get("promptFeedback", {}) if isinstance(data, dict) else {}
        reason = feedback.get("blockReason") if isinstance(feedback, dict) else None
        if reason:
            raise ValueError(f"Gemini did not process the document (block reason: {reason}).") from exc
        raise ValueError("Gemini returned an unexpected response structure.") from exc
    if not content.strip():
        raise ValueError("Gemini returned an empty response.")
    try:
        result = _json.loads(content)
    except _json.JSONDecodeError as exc:
        raise ValueError("Gemini response was not valid JSON. Run extraction again.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("fields"), dict):
        raise ValueError("Gemini response must contain a 'fields' object.")
    incoming = result["fields"]
    unknown = sorted(set(incoming) - set(ALIASES))
    if unknown:
        raise ValueError("Gemini returned unknown field names; response rejected.")
    fields: dict[str, str] = {}
    for key in ALIASES:
        value = incoming.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"Gemini returned a non-string value for '{key}'; response rejected.")

        value = value.strip()

        # Preserve blank as uncertainty; the model prompt reserves "-" for a clearly
        # unselected option. Conflating these states hid ambiguous readings.
        fields[key] = value

    # Normalize selected courses once, without comma-splitting course labels or
    # silently discarding an answer that differs from the allowed spelling.
    fields["Course Applied"] = _normalize_course_selection(
        fields.get("Course Applied", "")
    )

    fields = _normalize_fields(fields)
    return fields


def _parse_openrouter_response(data: dict[str, _Any]) -> dict[str, str]:
    """Parse OpenAI-compatible chat-completions response into the common fields schema."""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("AI provider returned an unexpected chat-completions response structure.") from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI provider returned an empty response.")
    # Some compatible endpoints wrap JSON in a markdown fence despite the instruction.
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    try:
        result = _json.loads(content.strip())
    except _json.JSONDecodeError as exc:
        raise ValueError("AI provider response was not valid JSON. Run extraction again.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("fields"), dict):
        raise ValueError("AI provider response must contain a 'fields' object.")
    incoming = result["fields"]
    unknown = sorted(set(incoming) - set(ALIASES))
    if unknown:
        raise ValueError("AI provider returned unknown field names; response rejected.")
    fields: dict[str, str] = {}
    for key in ALIASES:
        value = incoming.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"AI provider returned a non-string value for '{key}'; response rejected.")
        value = value.strip()
        # Preserve blank as uncertainty; "-" means visibly unselected only.
        fields[key] = value
    fields["Course Applied"] = _normalize_course_selection(fields.get("Course Applied", ""))
    return _normalize_fields(fields)


def _openai_compatible_image_parts(file_path: str | _Path) -> tuple[list[dict[str, _Any]], int]:
    """Prepare image data URLs for OpenAI-compatible vision APIs; render PDFs page-by-page."""
    path = _Path(file_path)
    ext = path.suffix.lower()
    parts: list[dict[str, _Any]] = []
    if ext == ".pdf":
        try:
            with _fitz.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                page_count = len(pdf)
                if page_count < 1:
                    raise ValueError("The PDF contains no pages.")
                if page_count > _MAX_PAGES:
                    raise ValueError(f"PDF has {page_count} pages; configured limit is {_MAX_PAGES}.")
                for page in pdf:
                    pix = page.get_pixmap(matrix=_fitz.Matrix(1.6, 1.6), alpha=False)
                    encoded = _base64.b64encode(pix.tobytes("png")).decode("ascii")
                    parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The uploaded PDF could not be rendered for the vision model.") from exc
    elif ext in {".jpg", ".jpeg", ".png"}:
        raw = path.read_bytes()
        if not raw:
            raise ValueError("The document file is empty.")
        mime = "image/png" if ext == ".png" else "image/jpeg"
        encoded = _base64.b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        page_count = 1
    else:
        raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted.")
    return parts, page_count


def extract_document_with_ai(file_path: str | _Path) -> tuple[dict[str, str], dict[str, _Any], dict[str, _Any]]:
    """Run the shared extraction prompt through the provider selected in .env."""
    from app.services.ai_provider import request_document

    settings = _load_ai_settings()
    if not settings.api_key:
        key_names = {
            "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY (or CLAUDE_API_KEY)", "mistral": "MISTRAL_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "openai_compatible": "AI_API_KEY",
        }
        raise RuntimeError(f"{key_names.get(settings.provider, 'AI API key')} is not configured in the backend environment.")

    started = _time.perf_counter()
    result = request_document(settings, file_path, _vision_prompt(), _MAX_PAGES)
    fields = _parse_openrouter_response({"choices": [{"message": {"content": result["content"]}}]})
    certificate_fields = {"Transfer Certificate", "Mark Sheets", "Community Certificate", "Income Certificate", "Passport-size Photo", "Aadhaar Proof", "PAN Proof", "Bank Passbook Proof"}
    missing = [key for key, value in fields.items() if not value or (value == "-" and key not in certificate_fields)]
    quality = {"total_fields": len(fields), "filled_fields": len(fields) - len(missing), "missing_fields": missing, "review_required": bool(missing)}
    usage = result.get("usage") or {}
    metrics = {
        "provider": settings.provider,
        "model": settings.model,
        "page_count": result["page_count"],
        "duration_ms": round((_time.perf_counter() - started) * 1000),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }
    return fields, quality, metrics
