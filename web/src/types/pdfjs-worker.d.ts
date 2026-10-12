/** pdf.js's parser, imported into the render worker to run in-thread (see pdf-render.worker.ts). */
declare module "pdfjs-dist/build/pdf.worker.min.mjs" {
  export const WorkerMessageHandler: unknown;
}
