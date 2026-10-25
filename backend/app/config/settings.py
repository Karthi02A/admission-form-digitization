import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
BATCHES = DATA / "batches"
FILES = DATA / "documents"
for p in (BATCHES, FILES):
    p.mkdir(parents=True, exist_ok=True)

MAX_FILES = 20
MAX_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "15")) * 1024 * 1024
MAX_PAGES = 15
ALLOWED = {".pdf", ".jpg", ".jpeg", ".png"}
ORIGINS = [
    x.strip()
    for x in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if x.strip()
]

# Field keys follow the printed labels on the fixed two-page admission form.
ALIASES = {
    "Application No": ["application no", "application number"],
    "Received By": ["received by"],
    "Received Date": ["received date"],
    "Course Applied": ["proposed study", "course applied"],
    "Student Name": ["student name", "name of student", "name of the student", "applicant name", "name"],
    "Roll No": ["roll no", "roll number"],
    "Date of Birth": ["date of birth", "date birth", "dob", "birth date"],
    "Nationality": ["nationality"],
    "Community": ["community category", "category", "caste"],
    "Gender": ["gender", "sex"],
    "Father's Name": ["father's / guardian's name", "father / guardian name", "father's guardian's name", "father's name", "father name", "name of father"],
    "Mother's Name": ["mother's name", "mother name", "name of mother"],
    "Religion": ["religion"],
    "Sub Caste": ["sub caste", "sub-caste"],
    "Aadhaar No": ["aadhaar no", "aadhaar number", "aadhar no"],
    "Address": ["address for communication", "communication address"],
    "Pan No": ["pan no", "pan number"],
    "Bank Name": ["bank name"],
    "Bank A/C No": ["bank a c no", "bank account no", "bank a/c no"],
    "IFSC Code": ["ifsc code"],
    "Father Mobile No": ["father mobile no", "father mobile number"],
    "Telephone No": ["tel no", "telephone no"],
    "Pincode": ["pincode", "pin code", "pin"],
    "Blood Group": ["blood group"],
    "Email": ["email id student", "student email", "email address", "email id"],
    "Mobile Number": ["mobile no student", "mobile number student", "student mobile no", "student mobile number", "student mobile", "mobile number"],
    "EMIS No": ["emis no", "emis number"],
    "Identification Mark 1": ["identification mark 1"],
    "Identification Mark 2": ["identification mark 2"],
    "Physically Challenged": ["physically challenged"],
    "Parents Occupation": ["parents occupation", "parent occupation"],
    "Income": ["income", "parents income"],
    "First Graduate": ["first graduate"],
    "Admission No": ["admission no", "admission number"],
    "Admission Date": ["admission date", "office use date"],
    "Admission Fee": ["admission fee"],
    "Last Studied Institution with Address": ["last studied institution with address", "last studied institution"],
    "XI Academic Records": [],
    "XII Academic Records": [],
    "XI Standard Register No": ["xi standard reg no", "xi reg no"],
    "XI Standard Marks Obtained": ["xi standard marks obtained"],
    "XI Standard Total Marks": ["xi standard total marks", "xi total marks"],
    "XII Standard Register No": ["xii standard reg no", "xii reg no"],
    "XII Standard Marks Obtained": ["xii standard marks obtained"],
    "XII Standard Total Marks": ["xii standard total marks", "xii total marks"],
    "XI Standard Maximum Marks": ["xi standard maximum marks", "xi maximum marks"],
    "XII Standard Maximum Marks": ["xii standard maximum marks", "xii maximum marks"],
    "XI Standard Percentage": ["xi standard percentage", "xi percentage"],
    "XII Standard Percentage": ["xii standard percentage", "xii percentage"],
    "Parent / Guardian Signature": ["signature of parent guardian", "signature of parent"],
    "Applicant Signature": ["signature of the applicant", "signature of applicant"],
    "Transfer Certificate": ["transfer certificate original", "transfer certificate"],
    "Mark Sheets": ["mark sheet x xi xii original", "mark sheets"],
    "Community Certificate": ["community certificate proof", "community certificate"],
    "Income Certificate": ["income certificate proof", "income certificate"],
    "Passport-size Photo": ["passport size photo", "passport-size photo", "passport photo"],
    "Aadhaar Proof": ["aadhaar proof", "aadhaar certificate", "aadhaar card proof"],
    "PAN Proof": ["pan proof", "pan card proof"],
    "Bank Passbook Proof": ["bank passbook proof", "bank passbook"],
}

CHECKBOX_FIELDS = {
    "Community",
    "Course Applied",
    "Gender",
    "Physically Challenged",
    "First Graduate",
    "Transfer Certificate",
    "Mark Sheets",
    "Community Certificate",
    "Income Certificate",
    "Passport-size Photo",
    "Aadhaar Proof",
    "PAN Proof",
    "Bank Passbook Proof",
}

COURSE_OPTIONS = [
    "B.A. Literature",
    "B.A. Arabic",
    "B.A. English",
    "B.A. Defence and Strategic Studies",
    "B.A. Criminology and Police Administration",
    "B.Sc. Hotel Management and Catering Science",
    "B.Sc. Visual Communication",
    "B.Sc. Data Science",
    "B.Sc. Cyber Security",
    "B.Sc. Computer Science",
    "B.Sc. Computer Application",
    "B.Sc. Information Technology",
    "B.Sc. Physics",
    "B.Sc. Forensic Science",
    "B.Sc. Chemistry",
    "B.Sc. Mathematics",
    "B.Sc. Biotechnology",
    "B.Sc. Microbiology",
    "B.Sc. Biochemistry",
    "B.Com. Commerce",
    "B.Com. Applied",
    "B.Com. Bank Management",
    "B.Com. Computer Application",
    "B.Com. Corporate Secretaryship",
    "B.B.A. Business Administration",
    "B.Sc. Artificial Intelligence and Machine Learning",
    "Diploma in Fire and Safety",
]
