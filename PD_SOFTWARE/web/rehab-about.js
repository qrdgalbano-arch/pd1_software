
const button = document.getElementById("rehab-about-open");
const dialog = document.getElementById("rehab-about-dialog");
const close = document.getElementById("rehab-about-close");
let previousFocus;
button?.addEventListener("click", () => {
  previousFocus = document.activeElement;
  if (!dialog.open) dialog.showModal();
});
close?.addEventListener("click", () => dialog.close());
dialog?.addEventListener("close", () => previousFocus?.focus());
