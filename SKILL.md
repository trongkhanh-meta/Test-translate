---
name: pdf-translate
description: Translate local, text-based PDFs into Vietnamese or another supported Latin-script language while preserving the original layout, formulas, tables, and figures. Use for PDF translation, batch translation, terminology-sensitive handoff translation, or diagnosing incomplete translated output. Do not use for image-only scans that need OCR or targets requiring CJK, right-to-left, or complex-script shaping.
license: AGPL-3.0-only
---

# PDF Translate

Translate a PDF with the bundled Code4Life engine. Keep the source file unchanged and produce a separate PDF with the same page structure.

When this skill runs inside the repository, first read
[`agent-knowledge/index.md`](agent-knowledge/index.md). For preservation or
layout work, load its PDF engine, regression, and validation routes. These are
the shared project instructions for Codex and Claude; do not duplicate them in
this entrypoint.

## Resolve the skill root

This skill may be installed globally while the user's files live elsewhere. Resolve the absolute directory containing this `SKILL.md` before running anything. Call its scripts and dependency files by absolute path; do not assume the current working directory is the skill directory.

Use the interpreter inside `<skill-root>/.venv`:

- Windows: `<skill-root>\.venv\Scripts\python.exe`
- macOS/Linux: `<skill-root>/.venv/bin/python`

## Choose a mode

| Mode | Translator | Use when |
| --- | --- | --- |
| Google (default) | `translate.google.com` | Books, batches, first drafts, or low token use |
| Google Medical | `translate.google.com` + `pdf2zh/medical_glossary.py` | Clinical, rehabilitation, or medical-education documents where Google alone mistranslates specialist vocabulary |
| Handoff | The active agent | Terminology, context, or translation quality matters beyond what a fixed glossary can cover |

Default to Google. Offer Google Medical (`--engine google-medical`) for medical or rehabilitation source material — it is the same request as Google mode, just with known clinical terms and abbreviations swapped for a curated Vietnamese translation before the request and restored after, so Google's general-purpose word choice never touches them. It costs nothing extra in time or tokens over plain Google mode. Offer handoff instead when the user asks for higher quality than a fixed glossary can give, rejects the result, or provides a short technical document where full sentence-level context matters.

## Boundaries

- Use the bundled `pdf2zh/` core. Never substitute the PyPI `pdf2zh` package; the runner checks version `1.9.11` and preservation ruleset `code4life-preservation-v1` and refuses an external core.
- Google and Google Medical mode both send extracted document text to Google. Tell the user before processing sensitive material (this includes identifiable patient information in clinical documents) and obtain explicit confirmation unless their request already authorizes that disclosure. Handoff mode does not contact Google.
- The medical glossary (`pdf2zh/medical_glossary.py`) is a fixed-translation term list, not a context-aware translator. It only overrides Google's word choice for the exact English terms and abbreviations it contains; everything else in the document is still translated by Google as usual. It can be edited directly to add, remove, or correct terms.
- Supported targets are the Latin-script codes enforced by `scripts/translate_pdf.py`. CJK, right-to-left, Thai, Devanagari, and other complex-shaping targets are rejected because the bundled font and layout engine cannot render them reliably.
- There is now OCR (`--ocr`) for image-only pages, but it is a positional approximation, not a text-layer-accurate translation: font size and line position are Tesseract's estimate of where a line sat on the rasterized page, not a real relayout. It also needs the Tesseract OCR engine installed and on PATH separately from this skill's own `.venv` (pip only installs the `pytesseract` wrapper around it, not the engine itself); if it is missing, translate_pdf.py raises a clear error rather than silently skipping those pages. See "OCR mode" below.
- Text inside detected tables, figures, contents pages, indexes, symbol lists, or references may intentionally remain in the source language. Report material untranslated regions as partial translation.
- Preserve the source. Write results to a separate output directory. Do not pass `--overwrite` without explicit replacement authorization.

Read [the preservation contract](references/preservation-rules.md) before changing layout behavior, diagnosing preserved pages, or investigating untranslated regions.

## Set up the runtime

Use Python 3.11 or 3.12. Create `<skill-root>/.venv` and install `<skill-root>/requirements.txt` if the environment is absent or stale. Keep this environment separate from the user's project.

The source distribution downloads layout and font assets on its first translation, so the first run needs network access and takes longer. The packaged Windows app already contains these assets.

Windows:

```powershell
python -m venv "<skill-root>\.venv"
& "<skill-root>\.venv\Scripts\python.exe" -m pip install -r "<skill-root>\requirements.txt"
```

macOS/Linux:

```bash
python3 -m venv "<skill-root>/.venv"
"<skill-root>/.venv/bin/python" -m pip install -r "<skill-root>/requirements.txt"
```

Shared runner options include `--target-language` (default `vi`), `--source-language auto`, one-based `--pages 1,3-5`, `--threads 1..8` (default `4`), `--ignore-cache`, and `--overwrite`.

## Google mode

Run one command per file. Use absolute paths for the input and output directory.

Windows:

```powershell
& "<skill-root>\.venv\Scripts\python.exe" "<skill-root>\scripts\translate_pdf.py" "<input.pdf>" --output-dir "<output-dir>"
```

macOS/Linux:

```bash
"<skill-root>/.venv/bin/python" "<skill-root>/scripts/translate_pdf.py" "<input.pdf>" --output-dir "<output-dir>"
```

For a batch, process files individually and report progress. A failure on one file must not stop the remaining files; collect and report all failures at the end.

## Google Medical mode

Same as Google mode, with `--engine google-medical` added. No other flags change.

Windows:

```powershell
& "<skill-root>\.venv\Scripts\python.exe" "<skill-root>\scripts\translate_pdf.py" "<input.pdf>" --engine google-medical --output-dir "<output-dir>"
```

macOS/Linux:

```bash
"<skill-root>/.venv/bin/python" "<skill-root>/scripts/translate_pdf.py" "<input.pdf>" --engine google-medical --output-dir "<output-dir>"
```

## OCR mode

Add `--ocr` to any of the modes above (Google or Google Medical; not meaningful with handoff, since handoff never sees the image-only pages in the first place) to translate text found on image-only pages. It requires the Tesseract OCR engine installed separately and on PATH — check with `tesseract --version` before relying on it; if that fails, tell the user to install Tesseract (README.md has platform-specific links) rather than retrying.

```bash
"<skill-root>/.venv/bin/python" "<skill-root>/scripts/translate_pdf.py" "<input.pdf>" --engine google --ocr --output-dir "<output-dir>"
```

Pages that already have a text layer are unaffected either way; `--ocr` only changes behavior on pages pdfminer finds no text on at all.

## Handoff mode

Handoff extracts translatable segments to JSONL, lets the active agent translate them, then rebuilds the PDF. Warn about token and time cost before starting a large document. For long documents, suggest a representative sample such as `--pages 1-5` first.

### 1. Extract

An output directory is not required during extraction because the pass-one PDF is discarded.

```text
<python> <skill-root>/scripts/translate_pdf.py <input.pdf> --engine handoff --emit-segments <segments.jsonl>
```

### 2. Translate

Read `segments.jsonl` in manageable batches. Write one JSON object per line to `translations.jsonl`:

```json
{"src":"exact source text","dst":"translated text"}
```

Copy each `src` value exactly. Preserve URLs, paths, identifiers, citation markers, and numbers.

Formula and code placeholders such as `<b0></b0>` are immutable. Every opening and closing tag must retain the same identifier, count, and order as the source. The loader rejects a record whose placeholders differ, leaving that segment untranslated.

Inline emphasis markers are immutable as balanced pairs: `<s1>...</s1>` is
bold, `<s2>...</s2>` is italic, and `<s3>...</s3>` is bold italic. Complete
style pairs may move with the translated phrase, but none may be dropped,
duplicated, or cross-nested. Invalid style markup leaves the segment
untranslated instead of silently losing emphasis.

### 3. Rebuild

```text
<python> <skill-root>/scripts/translate_pdf.py <input.pdf> --engine handoff --segments <translations.jsonl> --output-dir <output-dir> --emit-segments <still-missing.jsonl>
```

The command prints the remaining untranslated segment count. If it is nonzero, translate `still-missing.jsonl`, append valid records to `translations.jsonl`, and rebuild again. Stop only at zero or when a segment cannot be translated safely; then report the exact remaining limitation.

Extraction and rebuild each run the layout pass, so handoff uses roughly twice the local PDF processing of Google mode in addition to the agent's translation work.

## Verify before delivery

1. Confirm the output exists and the source still exists unchanged.
2. Confirm source and output page counts match.
3. Extract text page by page and check for substantial untranslated passages, missing formulas, damaged URLs, or lost identifiers.
4. When page rendering or image inspection is available, render every output page and inspect for blank pages, missing glyphs, clipping, overlap, and displaced tables or figures.
5. If full visual inspection is unavailable, say which checks were completed. Do not present a partially verified or partially translated file as fully complete.
