"""Prints JSON facts about a PDF (page count, page sizes in points, extracted text) for the printing spike."""

import json
import sys

from pypdf import PdfReader

reader = PdfReader(sys.argv[1])
print(
    json.dumps(
        {
            "pages": len(reader.pages),
            "sizes": [[round(float(p.mediabox.width), 1), round(float(p.mediabox.height), 1)] for p in reader.pages],
            "text": "\n".join((p.extract_text() or "") for p in reader.pages),
        }
    )
)
