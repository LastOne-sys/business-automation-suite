"""Generate a synthetic text-PDF fixture and check the real extraction path."""
import base64
from pathlib import Path
from reportlab.pdfgen import canvas
from core.server import extract_pdf
from core.domain import parse_invoice, validate_invoice, Invalid

folder=Path(__file__).resolve().parents[1]/'examples'
folder.mkdir(exist_ok=True)
path=folder/'sample-invoice.pdf'
c=canvas.Canvas(str(path));c.setFont('Helvetica-Bold',20);c.drawString(60,790,'DEMO INVOICE')
c.setFont('Helvetica',12)
lines=['Vendor: DEMO North Supply','Invoice: PDF-2026-042','Date: 2026-09-28',
       'Due: 2026-10-12','Net: 100.00','Tax: 20.00','Total: 120.00','Currency: EUR']
for index,line in enumerate(lines):c.drawString(60,740-index*28,line)
c.save()
result=extract_pdf({'file':base64.b64encode(path.read_bytes()).decode()})
fields=parse_invoice(result['text'])
assert fields['number']=='PDF-2026-042'
assert not validate_invoice(fields),validate_invoice(fields)
try:extract_pdf({'file':base64.b64encode(b'not a PDF').decode()})
except Invalid:pass
else:raise AssertionError('Invalid file accepted')
print('Text PDF extraction, field validation and invalid-file rejection passed.')
