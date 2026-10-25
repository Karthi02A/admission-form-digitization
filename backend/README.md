# Admission Form Digitization System

## Project folders

- `backend\` contains the FastAPI API, extraction pipeline, storage, and tests.
- `frontend\` contains the Next.js/TypeScript application.

## Run locally

Start the backend from the project root in PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend
```

Install and start the frontend in another PowerShell window:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open <http://127.0.0.1:3000/>. The frontend connects to the backend at
<http://127.0.0.1:8000> by default. Set `NEXT_PUBLIC_API_BASE_URL` or use the
`api` query parameter to change the API address. The backend root redirects to
the frontend; API documentation is at <http://127.0.0.1:8000/docs>. If the
backend virtual environment has not been prepared, install
`backend\requirements.txt` into it first.

## Review workflow

Select or drag in up to 20 PDF, JPG, JPEG, or PNG files (15 MB per file), then
choose **Extract**. Files are uploaded first and extracted individually, with
per-file status and errors. **Review** opens the selected original PDF in PDF.js
or image beside the ordered, editable field table. Edits are debounced and
saved through FastAPI; document changes and exports wait for pending saves.

The existing JSON persistence and API endpoints are retained. Set `DATA_DIR`
to use a different persistence directory. This storage is intended for a
single application instance and modest workloads; add authentication and
private storage before exposing real student records.

## Extraction status

PyMuPDF inspects PDFs page by page. OCR runs only on pages with large scanned
images; positioned embedded text fills only OCR gaps. PaddleOCR remains the
default baseline. Positioned-field limits use the actual page width rather
than the rightmost detected word, preventing sparse text-only documents from
truncating multiword values. An opt-in TrOCR candidate uses label-anchored
handwriting regions and batched CPU inference:

```powershell
$env:OCR_ENGINE = "trocr"
```

The first TrOCR run downloads `microsoft/trocr-base-handwritten` to the local
Hugging Face cache. It does not use reference workbook answers. Keep PaddleOCR
as the default unless the ten-PDF benchmark shows improved exact matches.
The measured BFS26001 TrOCR run produced 0/31 exact matches in 425.8 seconds,
compared with the Paddle baseline's 7/31; TrOCR is experimental and is not
recommended for production extraction.
Uncertain values remain editable for human review. Perspective correction is
applied to raster uploads only when OpenCV finds a clear page quadrilateral;
PDF geometry and original uploaded documents are preserved. Academic table
columns are separated with tabs in the editable multiline value.

Set up the CPU-only model dependencies in the backend virtual environment:

```powershell
py -3.13 -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

The model weights are downloaded on first TrOCR extraction, not during startup.
`TROCR_CPU_THREADS` optionally controls CPU threads; the default is capped at
four. `TROCR_MODEL` can select a local model directory for offline runs.

Local evaluation files contain student information. Keep them local and do
not commit or share them. The workbook is used only as a benchmark, never as
extraction input. Run the benchmark from the backend directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_extraction --diagnostics
```

The benchmark reports aggregate exact-match/non-empty counts, per-document
stage timings, memory, and redacted mismatch categories. Run separate benchmark
passes with `OCR_ENGINE=paddle` and `OCR_ENGINE=trocr`; both use the workbook
only after extraction. It runs all ten two-page forms and can take a long time
on CPU. Add `--student BFS26002` for one PDF or `--text-only` to evaluate
embedded text without OCR. The API logs model initialization, PDF inspection,
rendering, inference, mapping, persistence, and request totals separately.

## Frontend checks

```powershell
Set-Location .\frontend
npm run lint
npm run typecheck
npm run build
```

## API

- `POST /api/batches` creates a batch.
- `POST /api/batches/{id}/upload` accepts multipart `files`; add
  `?extract=false` to save files for later extraction.
- `POST /api/batches/{id}/documents/{doc_id}/extract` processes one saved
  document and returns its fields, status, and any extraction error.
- `GET /api/batches/{id}` returns documents and current field values.
- `GET /api/batches/{id}/documents/{doc_id}/file` previews the original.
- `PATCH /api/batches/{id}/documents/{doc_id}/fields/{field_name}` saves a
  correction using `{"value":"..."}`.
- `GET /api/batches/{id}/export.xlsx` and `/export.csv` export the batch.
- `DELETE /api/batches/{id}` removes that batch and only its stored files.
