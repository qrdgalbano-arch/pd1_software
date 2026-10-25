const accessTokenKey = "qmmc_staff_access_token";

const loginView = document.querySelector("#login-view");
const dashboardView = document.querySelector("#dashboard-view");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginError = document.querySelector("#login-error");
const dashboardError = document.querySelector("#dashboard-error");
const dashboardLoading = document.querySelector("#dashboard-loading");
const dashboardContent = document.querySelector("#dashboard-content");
const staffName = document.querySelector("#staff-name");
const logoutButton = document.querySelector("#logout-button");
const patientSearch = document.querySelector("#patient-search");
const patientTableBody = document.querySelector("#patient-table-body");
const patientEmpty = document.querySelector("#patient-empty");
const patientDetail = document.querySelector("#patient-detail");
const selectedPatientName = document.querySelector("#selected-patient-name");
const selectedPatientEmail = document.querySelector("#selected-patient-email");
const closePatientButton = document.querySelector("#close-patient-button");
const prescriptionList = document.querySelector("#prescription-list");
const patientFlagList = document.querySelector("#patient-flag-list");
const sessionTableBody = document.querySelector("#session-table-body");
let sessionStatusChart;

function getAccessToken() {
  return sessionStorage.getItem(accessTokenKey);
}

function setAccessToken(accessToken) {
  sessionStorage.setItem(accessTokenKey, accessToken);
}

function clearAccessToken() {
  sessionStorage.removeItem(accessTokenKey);
}

function showElement(element) {
  element.classList.remove("d-none");
}

function hideElement(element) {
  element.classList.add("d-none");
}

function showLoginError(message) {
  loginError.textContent = message;
  showElement(loginError);
}

function hideLoginError() {
  loginError.textContent = "";
  hideElement(loginError);
}

function showDashboardError(message) {
  dashboardError.textContent = message;
  showElement(dashboardError);
}

function hideDashboardError() {
  dashboardError.textContent = "";
  hideElement(dashboardError);
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

function formatDate(value) {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDuration(totalSeconds) {
  const seconds = Number(totalSeconds ?? 0);

  if (seconds < 60) {
    return `${seconds} sec`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;

  return remainder > 0
    ? `${minutes} min ${remainder} sec`
    : `${minutes} min`;
}

function statusBadge(status) {
  const classes = {
    completed: "text-bg-success",
    incomplete: "text-bg-warning",
    cancelled: "text-bg-secondary",
  };

  return `<span class="badge ${classes[status] || "text-bg-secondary"}">
    ${escapeHtml(status)}
  </span>`;
}

function flagBadge(flagType) {
  const labels = {
    missed_session: "Missed session",
    repeated_error: "Repeated error",
    incomplete_session: "Incomplete session",
    low_compliance: "Low compliance",
  };

  return `<span class="badge text-bg-danger">
    ${escapeHtml(labels[flagType] || flagType)}
  </span>`;
}

async function apiRequest(path, options = {}) {
  const accessToken = getAccessToken();

  if (!accessToken) {
    throw new Error("Your session has expired. Please sign in again.");
  }

  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(options.headers || {}),
    },
  });

  if (response.status === 401 || response.status === 403) {
    clearAccessToken();
    showLogin();
    throw new Error("Your session is no longer authorized. Please sign in again.");
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the fallback message.
    }

    throw new Error(message);
  }

  return response.json();
}

function showLogin() {
  hideDashboardError();
  hideDashboardError();
  hideElement(dashboardView);
  showElement(loginView);
  hideElement(patientDetail);
}

function showDashboard() {
  hideLoginError();
  hideElement(loginView);
  showElement(dashboardView);
}

function renderSummary(summary) {
  document.querySelector("#patient-count").textContent = summary.patient_count;
  document.querySelector("#prescription-count").textContent =
    summary.active_prescription_count;
  document.querySelector("#session-count").textContent =
    summary.recent_session_count;
  document.querySelector("#flag-count").textContent =
    summary.unresolved_flag_count;
}

function renderSessionStatusChart(summary) {
  const canvas = document.querySelector("#session-status-chart");
  const labels = summary.session_status_counts.map((item) => item.status);
  const values = summary.session_status_counts.map((item) => item.count);

  if (sessionStatusChart) {
    sessionStatusChart.destroy();
  }

  sessionStatusChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Sessions",
          data: values,
          backgroundColor: ["#198754", "#ffc107", "#6c757d"],
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0,
          },
        },
      },
    },
  });
}

function renderFlags(flags, container, showPatient = false) {
  if (!flags.length) {
    container.innerHTML =
      '<p class="text-secondary mb-0">No unresolved compliance flags.</p>';
    return;
  }

  container.innerHTML = flags
    .map(
      (flag) => `
        <div class="list-group-item px-0">
          <div class="d-flex flex-wrap justify-content-between gap-2 mb-2">
            ${flagBadge(flag.flag_type)}
            <small class="text-secondary">${formatDate(flag.created_at)}</small>
          </div>
          ${
            showPatient
              ? `<p class="fw-semibold mb-1">${escapeHtml(
                  flag.patient.full_name
                )}</p>`
              : ""
          }
          <p class="flag-message mb-0">${escapeHtml(flag.message)}</p>
        </div>
      `
    )
    .join("");
}

function renderPatients(patients) {
  patientTableBody.innerHTML = patients
    .map(
      (patient) => `
        <tr>
          <td>${escapeHtml(patient.full_name)}</td>
          <td>${escapeHtml(patient.email)}</td>
          <td>
            <span class="badge ${
              patient.is_active ? "text-bg-success" : "text-bg-secondary"
            }">
              ${patient.is_active ? "Active" : "Inactive"}
            </span>
          </td>
          <td class="text-end">
            <button
              class="btn btn-sm btn-primary"
              data-patient-id="${patient.id}"
              data-patient-name="${escapeHtml(patient.full_name)}"
              data-patient-email="${escapeHtml(patient.email)}"
              type="button"
            >
              View
            </button>
          </td>
        </tr>
      `
    )
    .join("");

  patientEmpty.classList.toggle("d-none", patients.length > 0);
}

function renderPrescriptions(prescriptions) {
  if (!prescriptions.length) {
    prescriptionList.innerHTML =
      '<p class="text-secondary mb-0">No prescriptions found.</p>';
    return;
  }

  prescriptionList.innerHTML = prescriptions
    .map(
      (prescription) => `
        <article class="border rounded p-3 mb-3 prescription-card">
          <div class="d-flex flex-wrap justify-content-between gap-2 mb-2">
            <h4 class="h6 mb-0">${escapeHtml(prescription.exercise.name)}</h4>
            <span class="badge ${
              prescription.is_active ? "text-bg-success" : "text-bg-secondary"
            }">
              ${prescription.is_active ? "Active" : "Inactive"}
            </span>
          </div>
          <p class="text-secondary small mb-2">
            ${escapeHtml(prescription.exercise.description)}
          </p>
          <p class="mb-0">
            ${prescription.repetitions_target} repetitions ·
            ${formatDuration(prescription.duration_limit_seconds)} ·
            ${escapeHtml(prescription.scheduled_days)}
          </p>
        </article>
      `
    )
    .join("");
}

function renderSessions(sessions) {
  if (!sessions.length) {
    sessionTableBody.innerHTML = `
      <tr>
        <td class="text-secondary" colspan="5">No sessions found.</td>
      </tr>
    `;
    return;
  }

  sessionTableBody.innerHTML = sessions
    .map(
      (session) => `
        <tr>
          <td>
            <div>${formatDate(session.device_recorded_at)}</div>
            <small class="text-secondary">
              ${escapeHtml(session.prescription.exercise.name)}
            </small>
          </td>
          <td>${statusBadge(session.status)}</td>
          <td>
            ${session.repetitions_completed}
            ${
              session.arom_classification
                ? `<div><small class="text-secondary">
                    Valid ${session.valid_repetitions} · Invalid ${
                      session.invalid_repetitions
                    } · Incomplete ${session.incomplete_repetitions}
                  </small></div>
                  <div><small class="text-secondary">AROM: ${escapeHtml(
                    session.arom_classification
                  )}${
                    session.peak_rom_degrees !== null
                      ? ` (peak ${Number(session.peak_rom_degrees).toFixed(1)}°)`
                      : ""
                  }</small></div>`
                : ""
            }
          </td>
          <td>${formatDuration(session.duration_seconds)}</td>
          <td>
            ${session.error_count}
            ${
              session.error_summary
                ? `<span class="text-secondary">— ${escapeHtml(
                    session.error_summary
                  )}</span>`
                : ""
            }
          </td>
        </tr>
      `
    )
    .join("");
}

async function loadPatientDetail(patient) {
  hideDashboardError();
  selectedPatientName.textContent = patient.full_name;
  selectedPatientEmail.textContent = patient.email;
  prescriptionList.innerHTML = '<p class="text-secondary">Loading…</p>';
  patientFlagList.innerHTML = '<p class="text-secondary">Loading…</p>';
  sessionTableBody.innerHTML = `
    <tr>
      <td class="text-secondary" colspan="5">Loading…</td>
    </tr>
  `;
  showElement(patientDetail);

  try {
    const [prescriptions, sessions, flags] = await Promise.all([
      apiRequest(`/staff/patients/${patient.id}/prescriptions`),
      apiRequest(`/staff/patients/${patient.id}/sessions`),
      apiRequest(`/staff/patients/${patient.id}/flags`),
    ]);

    renderPrescriptions(prescriptions);
    renderSessions(sessions);
    renderFlags(flags, patientFlagList);
    patientDetail.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showDashboardError(error.message);
  }
}

async function loadPatients(query = "") {
  const search = query.trim();
  const path = search
    ? `/staff/patients?query=${encodeURIComponent(search)}`
    : "/staff/patients";

  try {
    const patients = await apiRequest(path);
    renderPatients(patients);
  } catch (error) {
    showDashboardError(error.message);
  }
}

async function loadDashboard() {
  hideDashboardError();
  showElement(dashboardLoading);
  hideElement(dashboardContent);

  try {
    const [summary, flags, patients] = await Promise.all([
      apiRequest("/staff/dashboard/summary"),
      apiRequest("/staff/flags?limit=10"),
      apiRequest("/staff/patients"),
    ]);

    renderSummary(summary);
    renderSessionStatusChart(summary);
    renderFlags(flags, document.querySelector("#flag-list"), true);
    renderPatients(patients);

    hideElement(dashboardLoading);
    showElement(dashboardContent);
  } catch (error) {
    hideElement(dashboardLoading);
    showDashboardError(error.message);
  }
}

async function restoreSession() {
  if (!getAccessToken()) {
    showLogin();
    return;
  }

  try {
    const user = await apiRequest("/auth/me");

    if (user.role !== "staff") {
      clearAccessToken();
      showLoginError("This dashboard is available to staff accounts only.");
      showLogin();
      return;
    }

    staffName.textContent = user.full_name;
    showDashboard();
    await loadDashboard();
  } catch (error) {
    if (getAccessToken()) {
      showLoginError(error.message);
    }

    showLogin();
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideLoginError();
  loginButton.disabled = true;
  loginButton.textContent = "Signing in…";

  try {
    const formData = new URLSearchParams({
      username: document.querySelector("#email").value.trim(),
      password: document.querySelector("#password").value,
    });

    const response = await fetch("/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    });

    if (!response.ok) {
      let message = "Unable to sign in.";

      try {
        const body = await response.json();
        message = body.detail || message;
      } catch {
        // Keep the fallback message.
      }

      throw new Error(message);
    }

    const tokens = await response.json();
    setAccessToken(tokens.access_token);
    await restoreSession();
  } catch (error) {
    clearAccessToken();
    showLoginError(error.message);
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "Sign in";
  }
});

logoutButton.addEventListener("click", () => {
  clearAccessToken();
  loginForm.reset();
  showLogin();
});

patientSearch.addEventListener("input", () => {
  window.clearTimeout(patientSearch.searchTimeout);

  patientSearch.searchTimeout = window.setTimeout(() => {
    loadPatients(patientSearch.value);
  }, 250);
});

patientTableBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-patient-id]");

  if (!button) {
    return;
  }

  loadPatientDetail({
    id: Number(button.dataset.patientId),
    full_name: button.dataset.patientName,
    email: button.dataset.patientEmail,
  });
});

closePatientButton.addEventListener("click", () => {
  hideElement(patientDetail);
});

restoreSession();