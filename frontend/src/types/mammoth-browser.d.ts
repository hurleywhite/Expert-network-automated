/**
 * The mammoth browser build ships no type declarations of its own.
 * Only extractRawText is used here, against an ArrayBuffer.
 */
declare module 'mammoth/mammoth.browser.js' {
  export function extractRawText(input: { arrayBuffer: ArrayBuffer }): Promise<{
    value: string;
    messages: unknown[];
  }>;
}
