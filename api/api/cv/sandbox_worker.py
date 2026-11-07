"""Sandbox child: reads one JSON request on stdin, writes one JSON response
on stdout, exits. JSON only, never pickle: a compromised child must not hand
the parent executable data. Imports only the readers, nothing touching
settings, the database or the network.
"""

import base64
import json
import sys


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def handle(req: dict) -> dict:
    op = req["op"]
    if op == "docx":
        from api.cv import engine

        parts = engine.validate_and_open(
            _unb64(req["data"]), req.get("filename") or "source.docx"
        )
        return {"ir": engine.extract_ir(parts).model_dump(mode="json")}
    if op == "pdf":
        from api.cv import pdf_text

        return {"pages": pdf_text.extract_pages(_unb64(req["data"]))}
    raise ValueError(f"unknown op {op!r}")


def main() -> int:
    from api.cv import engine

    try:
        out = {"ok": handle(json.loads(sys.stdin.buffer.read()))}
    except engine.CvEngineError as exc:
        out = {"error": {"kind": "engine", "code": exc.code, "message": exc.message}}
    except MemoryError:
        out = {"error": {"kind": "limit", "code": "memory", "message": "out of memory"}}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
