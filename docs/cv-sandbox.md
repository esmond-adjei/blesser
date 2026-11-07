# Upload sandbox

Every uploaded DOCX or PDF is read in a short-lived child process
(`api/cv/sandbox.py` → `api/cv/sandbox_worker.py`): the DOCX security
gate and text extraction (`engine.py`), or the PDF text read
(`pdf_text.py`). Nothing renders or edits a document any more (#201): the
API turns the extracted text into Markdown itself.

| Control | How |
|---|---|
| No secrets | The child gets a scrubbed environment: `PATH`, a throwaway `HOME`/`TMPDIR`, `LANG`. No `DATABASE_URL`, `AUTH_SECRET`, API keys or provider config. |
| No network | `unshare --user --net` (unprivileged network namespace) when the kernel allows it. |
| CPU / memory / files | `setrlimit`: address space (1 GB), CPU seconds (30), output file size (200 MB), open files (256), no core dumps. |
| Wall time | Hard timeout (45 s) kills the **whole process group**. |
| Output | JSON only (base64 for bytes), never pickle. |
| Unprivileged | When the API runs as root (the Docker image), the child runs as the `cvsandbox` system user. |

## Failure contract

* Malformed or malicious input (zip bomb, XXE/DTD, macros, path
  traversal, symlinks, oversize entries, an unreadable or encrypted PDF,
  a PDF with no text layer…) → **400** with the reader's specific reason.
  Validation itself happens inside the sandbox.
* Resource or time limit hit → **422** "This document is too large or
  complex to process safely." / "…took too long and was stopped."

The API process never parses document XML or PDF itself.

## Checking isolation

The API logs `[cv-sandbox] mode=process network_isolated=true|false
unprivileged=true|false` at startup. In Docker, the default seccomp profile usually blocks
unprivileged user namespaces, so the log reads `network_isolated=false`
there: the child still has no secrets and runs under limits, but can
reach the network. To close that gap either allow user namespaces for
the API container, or run the API (or a dedicated document worker) on a
network with no egress.

`CV_SANDBOX=inline` runs the same code in-process for debugging only.
