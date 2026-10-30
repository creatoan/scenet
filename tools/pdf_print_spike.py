"""Compare ReportLab and a dependency-free PDF writer on one print fixture.

Run:
    python tools/pdf_print_spike.py direct --output /tmp/scenet-direct.pdf
    pip install reportlab
    python tools/pdf_print_spike.py reportlab --output /tmp/scenet-reportlab.pdf

This is deliberately a one-panel print-prepress spike, not the production emitter.
The same resolved fixture is used by both backends so geometry and ink intent can
be inspected side by side.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import zlib

PAGE_W = 612.0
PAGE_H = 792.0
BLEED = 9.0
TRIM = (BLEED, BLEED, PAGE_W - BLEED, PAGE_H - BLEED)
FIXTURE = (
    "q\n"
    "0 0 0 1 k\n"
    "/GSoverprint gs\n"
    "BT /F1 18 Tf 72 700 Td (SCENET PRINT SPIKE) Tj ET\n"
    "0.4 0 0 1 k\n"
    "72 430 468 210 re f\n"
    "0 0 0 1 k\n"
    "1 w 72 430 468 210 re S\n"
    "Q\n"
)


def _pdf_date() -> str:
    """Use SOURCE_DATE_EPOCH so PDF metadata is stable across repeated builds."""
    import datetime

    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    date = datetime.datetime.fromtimestamp(epoch, datetime.UTC)
    return date.strftime("D:%Y%m%d%H%M%SZ")


def direct_pdf() -> bytes:
    """Write a tiny PDF with explicit K-only lettering and overprint graphics state."""
    date = _pdf_date()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/TrimBox [9 9 603 783] /BleedBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> "
            b"/ExtGState << /GSoverprint 5 0 R >> >> /Contents 6 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /ExtGState /Type /ExtGState /OP true /op true /OPM 1 >>",
        (
            b"<< /Length "
            + str(len(FIXTURE.encode("ascii"))).encode()
            + b" >>\nstream\n"
            + FIXTURE.encode("ascii")
            + b"endstream"
        ),
        (
            b"<< /Title (Scenet PDF print spike) /Producer (Scenet spike) "
            + f"/CreationDate ({date}) /ModDate ({date}) ".encode()
            + b"/ID [<"
            + hashlib.sha256(FIXTURE.encode("ascii")).hexdigest()[:32].encode()
            + b"><"
            + hashlib.sha256(FIXTURE.encode("ascii")).hexdigest()[:32].encode()
            + b">] >>"
        ),
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 7 0 R "
            f"/ID [<{hashlib.sha256(FIXTURE.encode('ascii')).hexdigest()[:32]}>"
            f"<{hashlib.sha256(FIXTURE.encode('ascii')).hexdigest()[:32]}>] >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def reportlab_pdf() -> bytes:
    """Emit the identical fixture using ReportLab's public canvas API."""
    from io import BytesIO

    from reportlab.lib.colors import CMYKColor
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    doc = canvas.Canvas(
        stream,
        pagesize=(PAGE_W, PAGE_H),
        pageCompression=0,
        invariant=1,
        pdfVersion=(1, 4),
    )
    doc.setTitle("Scenet PDF print spike")
    doc.setAuthor("Scenet")
    doc.setTrimBox(TRIM)
    doc.setBleedBox((0, 0, PAGE_W, PAGE_H))
    doc.setFillOverprint(1)
    doc.setStrokeOverprint(1)
    doc.setFillColor(CMYKColor(0, 0, 0, 1))
    doc.setFont("Helvetica", 18)
    doc.drawString(72, 700, "SCENET PRINT SPIKE")
    doc.setFillColor(CMYKColor(0.4, 0, 0, 1))
    doc.rect(72, 430, 468, 210, fill=1, stroke=0)
    doc.setFillColor(CMYKColor(0, 0, 0, 1))
    doc.rect(72, 430, 468, 210, fill=0, stroke=1)
    doc.showPage()
    doc.save()
    data = stream.getvalue()
    return data


def inspect_pdf(data: bytes) -> dict[str, bool]:
    """Check the structural requirements that can be asserted without a preflight tool."""
    text = " ".join(data.decode("latin-1").split())
    return {
        "pdf_header": data.startswith(b"%PDF-"),
        "trim_box": "/TrimBox [9 9 603 783]" in text,
        "bleed_box": "/BleedBox [0 0 612 792]" in text,
        "k_only_operator": "0 0 0 1 k" in text,
        "overprint_state": "/OP true" in text and "/op true" in text,
        "reproducible_id_present": "/ID [" in text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=("direct", "reportlab"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = direct_pdf() if args.backend == "direct" else reportlab_pdf()
    args.output.write_bytes(data)
    print(f"backend={args.backend}")
    print(f"bytes={len(data)}")
    print(f"sha256={hashlib.sha256(data).hexdigest()}")
    for name, passed in inspect_pdf(data).items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    print("preflight=NOT RUN (use a PDF/X-capable preflight tool)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
