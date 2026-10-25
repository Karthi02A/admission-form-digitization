import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const worker = require.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
const destination = join(root, "public", "pdf.worker.min.mjs");

await mkdir(dirname(destination), { recursive: true });
await copyFile(worker, destination);