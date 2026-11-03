import mammoth from 'mammoth';

/**
 * Turns an uploaded requirements document into something Claude can read.
 *
 * PDFs are not text-extracted here. Claude accepts PDFs natively as a document
 * content block and sees layout, tables and headings, which a text extractor
 * would flatten and frequently scramble. Word files have no such path, so they
 * go through mammoth. Plain text formats are just decoded.
 */

/** Largest file we accept, before base64 encoding. */
export const MAX_FILE_BYTES = 3 * 1024 * 1024; // 3 MB

/**
 * Vercel caps a serverless request body at 4.5 MB and base64 inflates by ~4/3,
 * so 3 MB of file is about as much as can arrive intact.
 *
 * This is NOT the limit the user sees. The frontend accepts documents up to
 * 20 MB: anything above this threshold is text-extracted in the browser and
 * arrives as document_text instead, which is small whatever the source was.
 * A file reaching this function is therefore already meant to be under 3 MB,
 * and exceeding it means the client-side routing was bypassed.
 */
export const MAX_FILE_LABEL = '3 MB';

export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.csv', '.json', '.rtf'] as const;

/** Readable size that never rounds to look equal to the limit it exceeds. */
export function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export class DocumentError extends Error {
  statusCode = 400;
  constructor(message: string) {
    super(message);
    this.name = 'DocumentError';
  }
}

export interface UploadedFile {
  name: string;
  /** base64, with or without a data: URL prefix */
  data: string;
  type?: string;
}

/** Either plain text to inline in the prompt, or a PDF to hand to Claude whole. */
export type ExtractedDocument =
  | { kind: 'text'; text: string; source: string }
  | { kind: 'pdf'; base64: string; source: string };

function extensionOf(filename: string): string {
  const i = filename.lastIndexOf('.');
  return i === -1 ? '' : filename.slice(i).toLowerCase();
}

function decodeBase64(data: string): Buffer {
  // Accept both a bare base64 string and a data: URL, which is what
  // FileReader.readAsDataURL produces.
  const comma = data.indexOf(',');
  const payload = data.startsWith('data:') && comma !== -1 ? data.slice(comma + 1) : data;

  let buf: Buffer;
  try {
    buf = Buffer.from(payload, 'base64');
  } catch {
    throw new DocumentError('The uploaded file could not be decoded.');
  }
  if (buf.length === 0) throw new DocumentError('The uploaded file is empty.');
  return buf;
}

/** RTF carries its text inside control words; strip them rather than ship markup to Claude. */
function stripRtf(raw: string): string {
  return raw
    .replace(/\\'[0-9a-f]{2}/gi, ' ')
    .replace(/\\[a-z]+-?\d* ?/gi, ' ')
    .replace(/[{}]/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export async function extractDocument(file: UploadedFile): Promise<ExtractedDocument> {
  if (!file?.name) throw new DocumentError('The uploaded file is missing a filename.');
  if (!file?.data) throw new DocumentError('The uploaded file has no content.');

  const buffer = decodeBase64(file.data);

  if (buffer.length > MAX_FILE_BYTES) {
    throw new DocumentError(
      `That file is ${humanSize(buffer.length)}. Files over ${MAX_FILE_LABEL} must have their ` +
        'text extracted in the browser before upload — reload the page and try again, or paste the text.',
    );
  }

  const ext = extensionOf(file.name);

  if (ext === '.pdf') {
    // Guard against a mislabelled file: every real PDF starts with %PDF-.
    if (buffer.subarray(0, 5).toString('latin1') !== '%PDF-') {
      throw new DocumentError(`"${file.name}" is named .pdf but is not a PDF file.`);
    }
    return { kind: 'pdf', base64: buffer.toString('base64'), source: file.name };
  }

  if (ext === '.docx') {
    // .docx is a zip; it always starts with "PK". A .doc renamed to .docx will
    // not, and mammoth's own error for that case is not user-friendly.
    if (buffer.subarray(0, 2).toString('latin1') !== 'PK') {
      throw new DocumentError(
        `"${file.name}" is not a valid .docx file. If it is an older .doc, open it in Word and "Save As" .docx.`,
      );
    }
    let text: string;
    try {
      const result = await mammoth.extractRawText({ buffer });
      text = result.value;
    } catch {
      throw new DocumentError(`"${file.name}" could not be read. Try re-saving it as .docx, or paste the text.`);
    }
    if (!text.trim()) {
      throw new DocumentError(`"${file.name}" appears to contain no text.`);
    }
    return { kind: 'text', text, source: file.name };
  }

  if (ext === '.doc') {
    throw new DocumentError(
      'Legacy .doc files are not supported. Open it in Word and "Save As" .docx, or paste the text.',
    );
  }

  if ((ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
    const raw = buffer.toString('utf8');
    const text = ext === '.rtf' ? stripRtf(raw) : raw;
    if (!text.trim()) throw new DocumentError(`"${file.name}" appears to be empty.`);
    return { kind: 'text', text, source: file.name };
  }

  throw new DocumentError(
    `"${file.name}" is not a supported file type. Supported: ${ACCEPTED_EXTENSIONS.join(', ')}. ` +
      'You can also paste the text directly.',
  );
}
