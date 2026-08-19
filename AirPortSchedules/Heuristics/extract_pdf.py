from __future__ import unicode_literals, print_function
import os, io
import fitz  # pymupdf

def read_pdf_text(filepath):
    doc = fitz.open(filepath)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return '\n'.join(pages)

pdfs = [
    r'f:\Lectures\Facultative\Optimizers\Tasks\AirPortSchedules\Heuristics\FA45_A compact optimization model for the tail assignment problem.pdf',
    r'f:\Lectures\Facultative\Optimizers\Tasks\AirPortSchedules\Heuristics\08_chapter_4.pdf',
]

out_path = r'f:\Lectures\Facultative\Optimizers\Tasks\AirPortSchedules\Heuristics\pdf_extract.txt'

with io.open(out_path, 'w', encoding='utf-8') as out:
    for p in pdfs:
        name = os.path.basename(p)
        out.write('=== FILE: ' + name + ' ===\n')
        t = read_pdf_text(p)
        out.write(t)
        out.write('\n\n')

print('Done.')
