
// Synchronizes renderer scope metadata only; no clinical computations.
const scopeMap = {
  component: "component", asset: "leg", system: "whole_body"
};
let queue = Promise.resolve();
let lastSuccessfulScope = null;

function scopeMessage(text) {
  let element = document.getElementById("rehab-scope-status");
  const selector = document.getElementById("twin-design");
  if (!selector) return;
  if (!element) {
    element = document.createElement("p");
    element.id = "rehab-scope-status";
    element.className = "hint";
    element.setAttribute("role", "status");
    selector.insertAdjacentElement("afterend", element);
  }
  element.textContent = text;
}

function sendScope(force = false) {
  const selector = document.getElementById("twin-design");
  const scope = scopeMap[selector?.value];
  if (!scope) return;
  queue = queue.catch(() => {}).then(async () => {
    if (!force && lastSuccessfulScope === scope) return;
    try {
      const response = await fetch("/api/rehab/design-scope", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({design_scope: scope}),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      lastSuccessfulScope = scope;
      scopeMessage(`Scope: ${scope}. Evaluation is unchanged.`);
    } catch (error) {
      scopeMessage(
        "Design renders locally, but scope metadata could not be saved. " +
        "Check station connection."
      );
      console.warn("Design-scope synchronization:", error);
    }
  });
}

const selector = document.getElementById("twin-design");
selector?.addEventListener("change", () => sendScope());
sendScope(true);
window.addEventListener("online", () => sendScope(true));
window.addEventListener("focus", () => sendScope(true));

// Also catch programmatic selection updates after avatar initialization.
const live = document.getElementById("screen-live");
if (live) {
  new MutationObserver(() => {
    if (!live.hidden) sendScope();
  }).observe(live, {attributes: true, attributeFilter: ["hidden"]});
}

async function refreshReferences() {
  const dialog = document.getElementById("rehab-about-dialog");
  if (!dialog) return;
  let section = document.getElementById("rehab-current-config");
  if (!section) {
    section = document.createElement("section");
    section.id = "rehab-current-config";
    dialog.append(section);
  }

  section.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = "Current configuration — live";
  section.append(heading);

  function paragraph(text) {
    const p = document.createElement("p");
    p.textContent = text;
    section.append(p);
  }

  try {
    const response = await fetch("/api/rehab/config-status", {
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    paragraph("Clinical deployment: NOT APPROVED.");
    paragraph(data.disclaimer);
    paragraph(
      `Mode: ${data.unapproved_mode}; extension enabled: ` +
      `${data.extension_enabled}; config: ${data.config_version}.`
    );
    paragraph(
      `Reference edition: ${data.reference_edition ?? "Not set"}. ` +
      `${data.reference_verification ?? ""}`
    );
    paragraph(`Configuration SHA-256: ${data.config_sha256}`);
    paragraph(
      "Approval flags are not authenticated PT approvals. " +
      "Approved clinical execution is still unavailable."
    );

    const list = document.createElement("ul");
    for (const [name, status] of Object.entries(data.exercise_status)) {
      const item = document.createElement("li");
      item.textContent =
        `${name}: configured approval flag ${status.configured_approval_flag}; ` +
        "verified approval: false";
      list.append(item);
    }
    section.append(list);

    for (const ref of data.references) {
      const title = document.createElement("h3");
      title.textContent = ref.title;
      section.append(title);
      for (const key of ["use", "status", "limitation", "requested_rule"]) {
        if (ref[key]) paragraph(ref[key]);
      }
      if (typeof ref.url === "string" && ref.url.startsWith("https://")) {
        const a = document.createElement("a");
        a.textContent = "Open reference";
        a.href = ref.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        section.append(a);
      }
    }
  } catch (error) {
    paragraph(
      "Current configuration could not be loaded. " +
      "The installation snapshot above is not approval evidence."
    );
    console.warn("Reference refresh:", error);
  }
}

document.getElementById("rehab-about-open")
  ?.addEventListener("click", refreshReferences);
