// Starts the lazy PDF preview for any [data-pdf-preview] on the page or swapped into the dialog.

function start(root: ParentNode): void {
  const hosts = root.querySelectorAll<HTMLElement>("[data-pdf-preview]:not([data-pdf-started])");
  if (hosts.length === 0) return;
  for (const host of hosts) host.dataset.pdfStarted = "true";
  void import("./pdf-preview").then(({ renderPdf }) => {
    for (const host of hosts) void renderPdf(host);
  });
}

export function initPdfPreviews(): void {
  start(document);
  document.addEventListener("htmx:afterSwap", (event) => {
    const { target } = (event as CustomEvent<{ target: Element }>).detail;
    start(target);
  });
}
