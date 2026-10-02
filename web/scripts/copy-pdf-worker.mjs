// pdf.js renders in a web worker. Serve the worker that matches the installed pdfjs-dist from
// public/ (generated, git-ignored), so the viewer needs no CDN and works offline.
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const source = require.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
const target = path.resolve(here, "../public/pdf.worker.min.mjs");
await mkdir(path.dirname(target), { recursive: true });
await copyFile(source, target);
console.log("copied pdf.js worker to public/pdf.worker.min.mjs");
