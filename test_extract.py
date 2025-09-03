import sys
import os

print("Python:", sys.version)

camelot_available = False
try:
    import camelot  # noqa: F401
    camelot_available = True
except Exception as e:
    print("Camelot import failed:", repr(e))

print("Camelot available:", camelot_available)

import main

pdf_path = os.path.join(os.getcwd(), "Murphy bioloxi report - 082020255.pdf")
print("PDF path:", pdf_path)

text = main.extract_text_from_pdf(pdf_path)
lines = [ln for ln in (text or "").splitlines() if ln.strip()]
print("Extracted lines:", len(lines))
print("Sample lines (up to 10):")
for ln in lines[:10]:
    print("  ", ln)

print("\n=== Testing with fallback parsing ===")
claims, missed = main.parse_insurance_claims_with_fallback(text, pdf_path)
print("Parsed claims:", len(claims))
print("Pattern-missed lines:", len(missed))
print("Sample claims (up to 5):")
for row in claims[:5]:
    print("  ", row)

print("\n=== Testing layout-only parsing ===")
layout_claims, layout_missed = main.parse_insurance_claims_layout(pdf_path)
print("Layout parsed claims:", len(layout_claims))
print("Layout missed lines:", len(layout_missed))
print("Sample layout claims (up to 5):")
for row in layout_claims[:5]:
    print("  ", row)

