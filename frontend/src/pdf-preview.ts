// PDF preview (spec §12 rev 27): draws a document's pages on canvases with pdf.js, so a PDF is
// never served inline. A lazy chunk: main.ts imports it only when a [data-pdf-preview] appears.
// The view hands over a presigned GET (data-src); the bucket's CORS allows GET from the site.

import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

const MAX_PAGES = 20;
GlobalWorkerOptions.workerSrc = workerUrl;

function say(host: HTMLElement, text: string): void {
  const status = host.querySelector<HTMLElement>("[data-pdf-status]");
  if (status) status.textContent = text;
}

export async function renderPdf(host: HTMLElement): Promise<void> {
  const src = host.dataset.src;
  const pages = host.querySelector<HTMLElement>("[data-pdf-pages]");
  if (!src || !pages) {
    say(host, "We couldn't show this PDF. Download it instead.");
    return;
  }
  say(host, "Loading the PDF…");
  try {
    const response = await fetch(src);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = new Uint8Array(await response.arrayBuffer());
    const task = getDocument({ data });
    const pdf = await task.promise;
    const shown = Math.min(pdf.numPages, MAX_PAGES);
    const ratio = window.devicePixelRatio || 1;
    for (let number = 1; number <= shown; number += 1) {
      if (!host.isConnected) break; // the dialog closed
      const page = await pdf.getPage(number);
      const base = page.getViewport({ scale: 1 });
      const width = Math.max(pages.clientWidth, 1);
      const viewport = page.getViewport({ scale: (width / base.width) * ratio });
      const canvas = document.createElement("canvas");
      canvas.className = "pdf-preview__page";
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.setAttribute("role", "img");
      canvas.setAttribute("aria-label", `Page ${number} of ${pdf.numPages}`);
      pages.append(canvas);
      await page.render({ canvas, viewport }).promise;
    }
    say(
      host,
      pdf.numPages > shown
        ? `Showing the first ${shown} of ${pdf.numPages} pages. Download the file for the rest.`
        : `${pdf.numPages} ${pdf.numPages === 1 ? "page" : "pages"}`,
    );
    await task.destroy(); // frees the worker
  } catch {
    say(host, "We couldn't show this PDF. Download it instead.");
  }
}
