"""Focused regression tests for deterministic post-processing rules."""
import importlib.util
import sys
import types
from pathlib import Path

# Minimal settings stubs allow these pure-function tests to load the module
# without initializing the full application or making any AI/network calls.
app = types.ModuleType("app")
app.__path__ = []
config = types.ModuleType("app.config")
config.__path__ = []
settings = types.ModuleType("app.config.settings")
settings.ALIASES = {
    "Course Applied": [], "Transfer Certificate": [], "Mark Sheets": [],
    "Community Certificate": [], "Income Certificate": [],
    "Student Name": [], "Roll No": [], "Blood Group": [],
}
settings.CHECKBOX_FIELDS = {
    "Transfer Certificate", "Mark Sheets", "Community Certificate", "Income Certificate"
}
settings.MAX_PAGES = 15
settings.COURSE_OPTIONS = [
    "B.A. Criminology & Police Administration", "B.Sc. Forensic Science"
]
ai_settings = types.ModuleType("app.config.ai_settings")
ai_settings.load_ai_settings = lambda: None

sys.modules.update({
    "app": app,
    "app.config": config,
    "app.config.settings": settings,
    "app.config.ai_settings": ai_settings,
})

# Load the updated extraction module from the actual application location.
BACKEND_DIR = Path(__file__).resolve().parents[1]
EXTRACTION_FILE = BACKEND_DIR / "app" / "services" / "extraction.py"

if not EXTRACTION_FILE.is_file():
    raise FileNotFoundError(
        f"Cannot find extraction module at {EXTRACTION_FILE}. "
        "Ensure app/services/extraction.py exists."
    )

spec = importlib.util.spec_from_file_location("extraction_fixed", EXTRACTION_FILE)
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load extraction module from {EXTRACTION_FILE}")

module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_multiple_courses_are_preserved():
    result = module._normalize_fields({
        "Course Applied": "B.A. Criminology and Police Administration; B.Sc. Forensic Science"
    })
    assert result["Course Applied"] == (
        "B.A. Criminology & Police Administration; B.Sc. Forensic Science"
    )


def test_unmatched_course_is_not_silently_discarded():
    result = module._normalize_fields({"Course Applied": "Unlisted Course Name"})
    assert result["Course Applied"] == "Unlisted Course Name"


def test_ambiguous_certificate_value_is_preserved():
    result = module._normalize_fields({"Transfer Certificate": "uncertain"})
    assert result["Transfer Certificate"] == "uncertain"


def test_explicit_positive_certificate_is_canonicalized():
    result = module._normalize_fields({"Transfer Certificate": "checked"})
    assert result["Transfer Certificate"] == "Yes"


def test_identifier_is_not_reformatted():
    value = "BPC 26008 BFS 26008"
    result = module._normalize_fields({"Roll No": value})
    assert result["Roll No"] == value


def test_invalid_blood_group_is_not_erased():
    value = "A positive"
    result = module._normalize_fields({"Blood Group": value})
    # Invalid blood group is retained for review instead of silently discarded.
    assert result["Blood Group"] == value


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"{len(tests)} tests passed")
