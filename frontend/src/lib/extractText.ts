/**
 * Browser-side text extraction for large documents.
 *
 * Vercel caps a function request body at 4.5 MB and base64 inflates by about a
 * third, so anything over ~3 MB cannot be posted to the API as a file. Those
 * documents are read here instead and only their text is sent, which is small
 * however large the source was.
 *
 * Smaller files still go to the server whole — a PDF under the threshold is
 * handed to Claude natively, which reads layout, tables and headings that this
 * extractor would flatten.
 *
 * pdf.js and mammoth are both loaded on demand: neither is in the main bundle.
 */

/** Above this, extract in the browser instead of uploading the file. */
export const INLINE_UPLOAD_LIMIT = 3 * 1024 * 1024;

export class ExtractionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExtractionError';
  }
}

function extensionOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i === -1 ? '' : name.slice(i).toLowerCase();
}

async function readAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new ExtractionError(`Could not read ${file.name}.`));
    reader.onload = () => resolve(String(reader.result || ''));
    reader.readAsText(file);
  });
}

function stripRtf(raw: string): string {
  return raw
    .replace(/\\'[0-9a-f]{2}/gi, ' ')
    .replace(/\\[a-z]+-?\d* ?/gi, ' ')
    .replace(/[{}]/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function extractPdf(file: File): Promise<string> {
  const pdfjs = await import('pdfjs-dist');

  // Vite resolves this to a hashed asset URL at build time; without it pdf.js
  // tries to fetch a worker from a path that does not exist in the bundle.
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
  ).toString();

  const buffer = await file.arrayBuffer();
  const task = pdfjs.getDocument({ data: new Uint8Array(buffer) });
  const doc = await task.promise;

  const pages: string[] = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const text = content.items
      .map((item: any) => ('str' in item ? item.str : ''))
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (text) pages.push(text);
  }
  // destroy() is on the loading task, not the document proxy; it releases the
  // worker, which otherwise stays alive for the life of the page.
  await task.destroy();

  if (!pages.length) {
    throw new ExtractionError(
      `No text could be read from ${file.name}. If it is a scan, it needs OCR first — ` +
        'or paste the key requirements as text.',
    );
  }
  return pages.join('\n\n');
}

async function extractDocx(file: File): Promise<string> {
  const mammoth = await import('mammoth/mammoth.browser.js');
  const buffer = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer: buffer });
  const text = String(result?.value || '');
  if (!text.trim()) throw new ExtractionError(`${file.name} appears to contain no text.`);
  return text;
}

/** Extracts a large document's text in the browser. */
export async function extractTextInBrowser(file: File): Promise<string> {
  const ext = extensionOf(file.name);

  try {
    if (ext === '.pdf') return await extractPdf(file);
    if (ext === '.docx') return await extractDocx(file);
    if (ext === '.rtf') return stripRtf(await readAsText(file));
    return await readAsText(file);
  } catch (err: any) {
    if (err instanceof ExtractionError) throw err;
    throw new ExtractionError(
      `Could not read ${file.name}: ${err?.message || 'unknown error'}. Try pasting the text instead.`,
    );
  }
}
