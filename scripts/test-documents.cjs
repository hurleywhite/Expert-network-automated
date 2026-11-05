#!/usr/bin/env node
/**
 * Tests api/_lib/documents.ts against real files.
 *
 *   node scripts/test-documents.cjs
 *
 * Builds a genuine .docx (a real OOXML zip, via jszip) and a real PDF, plus
 * the malformed and oversized cases, and checks extraction and every rejection
 * message. No network and no database. Exits non-zero on failure.
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
// Compile inside the repo so the output can resolve node_modules (mammoth).
const OUT = fs.mkdtempSync(path.join(ROOT, '.tmp-test-'));
process.on('exit', () => fs.rmSync(OUT, { recursive: true, force: true }));

try {
  execFileSync('npx', ['tsc', '--outDir', OUT], { cwd: ROOT, stdio: 'pipe' });
} catch (e) {
  console.error('TypeScript compilation failed:\n' + (e.stdout || e.message));
  process.exit(2);
}

const { extractDocument, MAX_FILE_BYTES } = require(path.join(OUT, 'api', '_lib', 'documents.js'));
const JSZip = require(path.join(ROOT, 'node_modules', 'jszip'));

let fail = 0;
const ok = (m) => console.log(`  \x1b[32mPASS\x1b[0m  ${m}`);
const bad = (m) => { fail++; console.log(`  \x1b[31mFAIL\x1b[0m  ${m}`); };
const section = (m) => console.log(`\n\x1b[1m${m}\x1b[0m`);
const b64 = (buf) => Buffer.from(buf).toString('base64');

/** A real .docx: the minimum set of OOXML parts Word and mammoth both accept. */
async function buildDocx(paragraphs) {
  const zip = new JSZip();
  zip.file('[Content_Types].xml',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`);
  zip.folder('_rels').file('.rels',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`);
  const body = paragraphs.map((t) => `<w:p><w:r><w:t>${t}</w:t></w:r></w:p>`).join('');
  zip.folder('word').file('document.xml',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${body}</w:body></w:document>`);
  return zip.generateAsync({ type: 'nodebuffer' });
}

/** A real, minimal single-page PDF. */
function buildPdf(text) {
  const objs = [
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
    '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
    '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n',
    `4 0 obj\n<< /Length ${text.length + 44} >>\nstream\nBT /F1 12 Tf 72 720 Td (${text}) Tj ET\nendstream\nendobj\n`,
    '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [];
  for (const o of objs) { offsets.push(pdf.length); pdf += o; }
  const xref = pdf.length;
  pdf += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) pdf += String(off).padStart(10, '0') + ' 00000 n \n';
  pdf += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf, 'latin1');
}

async function expectOk(label, file, check) {
  try {
    const r = await extractDocument(file);
    const problem = check(r);
    problem ? bad(`${label} — ${problem}`) : ok(label);
  } catch (e) {
    bad(`${label} — threw: ${e.message}`);
  }
}

async function expectReject(label, file, pattern) {
  try {
    await extractDocument(file);
    bad(`${label} — expected a rejection, got success`);
  } catch (e) {
    if (e.name !== 'DocumentError') return bad(`${label} — wrong error type: ${e.name}`);
    pattern.test(e.message) ? ok(`${label} — "${e.message.slice(0, 62)}…"`)
                            : bad(`${label} — message did not match: ${e.message}`);
  }
}

(async () => {
  section('Real documents');

  const docx = await buildDocx(['Expert Network Brief', 'We need published authors.', 'Self-published counts.']);
  await expectOk('.docx extracts its text', { name: 'brief.docx', data: b64(docx) }, (r) =>
    r.kind !== 'text' ? `kind was ${r.kind}` :
    !r.text.includes('published authors') ? `missing body text: ${JSON.stringify(r.text.slice(0, 80))}` :
    !r.text.includes('Expert Network Brief') ? 'missing heading' : null);

  await expectOk('.pdf is passed through for GPT-6 to read', { name: 'brief.pdf', data: b64(buildPdf('Published authors')) }, (r) =>
    r.kind !== 'pdf' ? `kind was ${r.kind}, expected pdf` :
    Buffer.from(r.base64, 'base64').subarray(0, 5).toString() !== '%PDF-' ? 'base64 is not a PDF' : null);

  await expectOk('.txt decodes', { name: 'brief.txt', data: b64(Buffer.from('Published authors (self-published)')) },
    (r) => (r.kind === 'text' && r.text.includes('self-published')) ? null : 'text not decoded');

  await expectOk('.md decodes', { name: 'brief.md', data: b64(Buffer.from('# Brief\n\n- Authors')) },
    (r) => (r.kind === 'text' && r.text.includes('# Brief')) ? null : 'markdown not decoded');

  await expectOk('.rtf has control words stripped', {
    name: 'brief.rtf',
    data: b64(Buffer.from('{\\rtf1\\ansi\\deff0 {\\fonttbl}\\f0\\fs24 Published authors wanted.}')),
  }, (r) => !r.text.includes('Published authors wanted') ? `text lost: ${JSON.stringify(r.text)}`
          : /\\rtf1|\\fonttbl|\\fs24/.test(r.text) ? `markup survived: ${JSON.stringify(r.text)}` : null);

  await expectOk('data: URL prefix is accepted', {
    name: 'brief.txt',
    data: 'data:text/plain;base64,' + b64(Buffer.from('Authors')),
  }, (r) => r.text.includes('Authors') ? null : 'prefix not stripped');

  section('Rejections');

  await expectReject('a .doc is refused with the fix',
    { name: 'old.doc', data: b64(Buffer.from('legacy')) }, /Save As.*\.docx/i);

  await expectReject('a .doc renamed to .docx is caught',
    { name: 'fake.docx', data: b64(Buffer.from('\xD0\xCF\x11\xE0 not a zip', 'latin1')) }, /not a valid \.docx/i);

  await expectReject('a non-PDF named .pdf is caught',
    { name: 'fake.pdf', data: b64(Buffer.from('just text')) }, /named \.pdf but is not a PDF/i);

  await expectReject('an unsupported type lists what works',
    { name: 'sheet.xlsx', data: b64(Buffer.from('PK...')) }, /not a supported file type.*\.pdf/is);

  await expectReject('an oversized file reports its size and the limit',
    { name: 'big.pdf', data: b64(Buffer.alloc(MAX_FILE_BYTES + 1024, 0x41)) }, /3\.00 MB.*over 3 MB.*extracted in the browser/is);

  await expectReject('an empty file is refused',
    { name: 'empty.txt', data: '' }, /no content|empty/i);

  await expectReject('a whitespace-only file is refused',
    { name: 'blank.txt', data: b64(Buffer.from('   \n\n  ')) }, /empty/i);

  await expectReject('a missing filename is refused',
    { name: '', data: b64(Buffer.from('x')) }, /filename/i);

  section('Boundary');
  await expectOk('a file exactly at the limit is accepted',
    { name: 'exact.txt', data: b64(Buffer.alloc(MAX_FILE_BYTES, 0x41)) },
    (r) => r.kind === 'text' ? null : 'rejected at exactly the limit');

  console.log(fail === 0 ? '\n\x1b[32mAll document checks passed.\x1b[0m\n'
                         : `\n\x1b[31m${fail} check(s) failed.\x1b[0m\n`);
  process.exit(fail ? 1 : 0);
})();
