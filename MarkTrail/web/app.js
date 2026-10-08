const state = {
  user: null,
  navView: "home",
  assessments: [],
  batches: [],
  reports: [],
  adminUsers: [],
  adminCourses: [],
  adminBatches: []
};

const $ = (selector) => document.querySelector(selector);

function toast(message, type = "success") {
  const node = document.createElement("div");
  node.className = "toast " + type;
  node.textContent = message;
  $("#toast-region").appendChild(node);
  setTimeout(() => node.remove(), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "Request failed.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function badge(value) {
  const map = {
    VERIFIED: ["success", "Verified / published"],
    SUBMITTED: ["warning", "Awaiting review"],
    AMENDED: ["info", "Amended / review needed"],
    OPEN: ["warning", "Open"],
    PENDING_REVIEW: ["info", "Pending review"],
    RESOLVED: ["success", "Resolved"],
    MISSING: ["warning", "Missing"],
    RECORDED: ["success", "Recorded"],
    NO_MARK: ["info", "No mark awarded"],
    CONFIRMED: ["success", "Chain confirmed"],
    LOCAL_ONLY: ["muted", "Local-only"],
    ERROR: ["warning", "Chain error"],
    PENDING: ["warning", "Chain pending"]
  };
  const entry = map[value] || ["muted", value || "Unknown"];
  return '<span class="badge ' + entry[0] + '">' + esc(entry[1]) + "</span>";
}

function showView(view) {
  state.navView = view;
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.add("hidden"));
  const role = state.user.role;
  const panelMap = {
    student: { home: "student-panel", marks: "student-panel", reports: "student-panel", audit: "audit-panel" },
    lecturer: { home: "lecturer-panel", batches: "lecturer-panel", reports: "lecturer-panel", audit: "audit-panel" },
    reviewer: { home: "reviewer-panel", verify: "reviewer-panel", audit: "audit-panel" },
    admin: { home: "admin-panel", setup: "admin-panel", audit: "audit-panel" }
  };
  const id = panelMap[role]?.[view] || panelMap[role]?.home;
  if (id) $("#" + id).classList.remove("hidden");
  document.querySelectorAll("#nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  updatePageHeading(view);
}

function updatePageHeading(view) {
  const titles = {
    home: ["Dashboard", "The current state of your marks workflow."],
    marks: ["My marks", "See what's published and what still needs attention."],
    reports: ["Mark issues", "Track reported missing marks to resolution."],
    batches: ["Assessment batches", "Submit and inspect lecturer batches."],
    verify: ["Verification queue", "Review batches before they become published."],
    setup: ["Institution setup", "Users, courses, rosters, and assessments."],
    audit: ["Audit trail", "Trace a batch revision by revision."]
  };
  const item = titles[view] || titles.home;
  $("#page-title").textContent = item[0];
  $("#page-subtitle").textContent = item[1];
}

function buildNav() {
  const role = state.user.role;
  const views = {
    student: [["home", "Dashboard"], ["marks", "My marks"], ["audit", "Audit"]],
    lecturer: [["home", "Dashboard"], ["batches", "Batches"], ["reports", "Issues"], ["audit", "Audit"]],
    reviewer: [["home", "Dashboard"], ["verify", "Verify"], ["audit", "Audit"]],
    admin: [["home", "Dashboard"], ["setup", "Setup"], ["audit", "Audit"]]
  };
  $("#nav").innerHTML = (views[role] || [])
    .map(([value, label]) => '<button data-view="' + value + '">' + label + "</button>")
    .join("");
  $("#nav").querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      showView(button.dataset.view);
      loadCurrentView();
    });
  });
}

function renderStats(dashboard) {
  const counts = dashboard.counts || {};
  const role = dashboard.user.role;
  const entries =
    role === "student"
      ? [["Assessments", counts.assessments], ["Missing", counts.missing]]
      : role === "lecturer"
        ? [["Batches", counts.batches], ["Open issues", counts.issues]]
        : role === "reviewer"
          ? [["Pending verification", counts.pending_verification]]
          : [["Users", counts.users], ["Courses", counts.courses], ["Assessments", counts.assessments], ["Open issues", counts.issues]];

  $("#dashboard-stats").innerHTML = entries
    .map(([label, value]) => '<div class="stat"><strong>' + esc(value) + '</strong><span>' + esc(label) + "</span></div>")
    .join("");

  const chain = dashboard.chain || {};
  const indicator = $("#chain-indicator");
  indicator.textContent = chain.enabled ? chain.label : "Local-only audit mode";
  indicator.className = "pill " + (chain.enabled ? "success" : "neutral");
  if (chain.error) {
    indicator.textContent = "Chain unavailable";
    indicator.className = "pill warning";
  }
}

async function loadDashboard() {
  const dashboard = await api("/api/dashboard");
  state.user = dashboard.user;
  $("#user-chip").textContent = dashboard.user.full_name + " · " + dashboard.user.role;
  renderStats(dashboard);
  buildNav();
  showView("home");
}

async function loadStudent() {
  const [marksData, reportsData] = await Promise.all([
    api("/api/student/marks"),
    api("/api/student/reports")
  ]);

  $("#student-marks").innerHTML =
    marksData.marks.length === 0
      ? '<div class="card"><p class="muted">No assessments found.</p></div>'
      : "<table><thead><tr><th>Course</th><th>Assessment</th><th>Mark</th><th>Status</th><th>Batch</th></tr></thead><tbody>" +
        marksData.marks
          .map((mark) => {
            const action =
              mark.status === "MISSING" && mark.batch_status === "VERIFIED"
                ? '<button class="button secondary" data-report="' + esc(mark.assessment_id) + '">Report missing</button>'
                : "";
            const display =
              mark.status === "MISSING"
                ? "—"
                : Number(mark.mark).toFixed(mark.mark % 1 ? 2 : 0) + "/" + mark.max_mark;
            return (
              "<tr><td>" +
              esc(mark.course) +
              "</td><td>" +
              esc(mark.assessment) +
              "</td><td><strong>" +
              display +
              "</strong></td><td>" +
              badge(mark.status) +
              "</td><td>" +
              badge(mark.batch_status) +
              " " +
              action +
              "</td></tr>"
            );
          })
          .join("") +
        "</tbody></table>";

  $("#student-marks").querySelectorAll("[data-report]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/student/reports", {
          method: "POST",
          body: JSON.stringify({ assessment_id: button.dataset.report })
        });
        toast("Missing-mark report opened.");
        await loadStudent();
        await loadDashboard();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  $("#student-reports").innerHTML =
    reportsData.reports.length === 0
      ? '<div class="card"><p class="muted">No reports yet.</p></div>'
      : reportsData.reports
          .map(
            (report) =>
              '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
              esc(report.course + " · " + report.assessment) +
              '</div><div class="muted">Opened ' +
              esc(report.opened_at) +
              '</div></div>' +
              badge(report.status) +
              '</div><p class="muted">' +
              esc(report.lecturer_note || "No resolution note yet.") +
              "</p></div>"
          )
          .join("");
}

async function loadLecturer() {
  const [assessmentsData, batchesData, reportsData] = await Promise.all([
    api("/api/lecturer/assessments"),
    api("/api/lecturer/batches"),
    api("/api/lecturer/reports")
  ]);

  state.assessments = assessmentsData.assessments;
  state.batches = batchesData.batches;
  state.reports = reportsData.reports;

  $("#lecturer-assessment").innerHTML = state.assessments
    .map((a) => {
      const suffix = a.batch_id
        ? " · " + a.batch_status + " · revision " + a.revision
        : " · not submitted";
      return '<option value="' + esc(a.id) + '"' + (a.batch_id ? " disabled" : "") + ">" + esc(a.course + " · " + a.name + suffix) + "</option>";
    })
    .join("");

  $("#lecturer-reports").innerHTML =
    state.reports.length === 0
      ? '<div class="card"><p class="muted">No missing-mark issues.</p></div>'
      : state.reports
          .map((report) => {
            let actions = "";
            if (report.status === "OPEN") {
              actions =
                '<div class="actions"><button class="button primary" data-resolve-mark="' +
                esc(report.id) +
                '">Enter mark</button><button class="button secondary" data-no-mark="' +
                esc(report.id) +
                '">No mark awarded</button></div>';
            }
            return (
              '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
              esc(report.student_name + " · " + report.student_username) +
              '</div><div class="muted">' +
              esc(report.course + " · " + report.assessment) +
              " · report " +
              esc(report.id) +
              "</div></div>" +
              badge(report.status) +
              '</div><p class="muted">Opened ' +
              esc(report.opened_at) +
              "</p>" +
              actions +
              "</div>"
            );
          })
          .join("");

  $("#lecturer-reports").querySelectorAll("[data-resolve-mark]").forEach((button) => {
    button.addEventListener("click", () => resolveReport(button.dataset.resolveMark, true));
  });
  $("#lecturer-reports").querySelectorAll("[data-no-mark]").forEach((button) => {
    button.addEventListener("click", () => resolveReport(button.dataset.noMark, false));
  });

  $("#lecturer-batches").innerHTML =
    state.batches.length === 0
      ? '<div class="card"><p class="muted">No submitted batches.</p></div>'
      : "<table><thead><tr><th>Course</th><th>Assessment</th><th>Status</th><th>Revision</th><th>Chain</th><th>Batch</th></tr></thead><tbody>" +
        state.batches
          .map(
            (batch) =>
              "<tr><td>" +
              esc(batch.course) +
              "</td><td>" +
              esc(batch.assessment) +
              "</td><td>" +
              badge(batch.status) +
              "</td><td>" +
              esc(batch.revision) +
              "</td><td>" +
              badge(batch.chain_state) +
              "</td><td><button class=\"button secondary\" data-audit-batch=\"" +
              esc(batch.id) +
              '">Audit</button></td></tr>'
          )
          .join("") +
        "</tbody></table>";

  $("#lecturer-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

async function resolveReport(reportId, withMark) {
  let mark = null;
  if (withMark) {
    const raw = window.prompt("Enter the mark:", "17");
    if (raw === null) return;
    mark = Number(raw);
    if (!Number.isFinite(mark)) {
      toast("Enter a numeric mark.", "error");
      return;
    }
  }
  const note = window.prompt(
    withMark ? "Resolution note:" : "Why was no mark awarded?",
    withMark ? "Missing mark restored." : "Student did not have an awarded mark."
  );
  if (note === null) return;

  try {
    await api("/api/lecturer/reports/" + encodeURIComponent(reportId) + "/resolve", {
      method: "POST",
      body: JSON.stringify({
        resolution_type: withMark ? "MARK_ENTERED" : "NO_MARK_AWARDED",
        mark,
        note
      })
    });
    toast("Resolution recorded. Reviewer approval is now required.");
    await loadLecturer();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadReviewer() {
  const data = await api("/api/reviewer/batches");
  state.batches = data.batches;

  $("#reviewer-batches").innerHTML =
    state.batches.length === 0
      ? '<div class="card"><p class="muted">No batches found.</p></div>'
      : state.batches
          .map((batch) => {
            const canVerify = ["SUBMITTED", "AMENDED"].includes(batch.status) && ["CONFIRMED", "LOCAL_ONLY"].includes(batch.chain_state);
            const action = canVerify
              ? '<button class="button primary" data-verify="' + esc(batch.id) + '">Verify & publish</button>'
              : "";
            const retry =
              batch.chain_state === "ERROR"
                ? '<button class="button secondary" data-retry="' + esc(batch.id) + '">Retry chain</button>'
                : "";
            return (
              '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
              esc(batch.course + " · " + batch.assessment) +
              '</div><div class="muted">' +
              esc(batch.lecturer_name) +
              " · revision " +
              esc(batch.revision) +
              " · " +
              esc(batch.student_count) +
              " students</div></div>" +
              badge(batch.status) +
              '</div><p class="muted">Chain: ' +
              badge(batch.chain_state) +
              "</p><div class=\"actions\">" +
              action +
              retry +
              '<button class="button secondary" data-audit-batch="' +
              esc(batch.id) +
              '">Audit</button></div></div>'
            );
          })
          .join("");

  $("#reviewer-batches").querySelectorAll("[data-verify]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/reviewer/batches/" + encodeURIComponent(button.dataset.verify) + "/verify", { method: "POST" });
        toast("Batch verified and published.");
        await loadReviewer();
        await loadDashboard();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  $("#reviewer-batches").querySelectorAll("[data-retry]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/reviewer/batches/" + encodeURIComponent(button.dataset.retry) + "/retry-chain", { method: "POST" });
        toast("Blockchain operation retried.");
        await loadReviewer();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  $("#reviewer-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

async function loadAdmin() {
  const [users, courses, batches] = await Promise.all([
    api("/api/admin/users"),
    api("/api/admin/courses"),
    api("/api/admin/batches")
  ]);
  state.adminUsers = users.users;
  state.adminCourses = courses.courses;
  state.adminBatches = batches.batches;

  const lecturers = state.adminUsers.filter((user) => user.role === "lecturer");
  $("#course-lecturer").innerHTML = lecturers.map(
    (user) => '<option value="' + esc(user.id) + '">' + esc(user.full_name + " · " + user.username) + "</option>"
  ).join("");

  const courses = state.adminCourses;
  $("#enroll-course").innerHTML = courses.map(
    (course) => '<option value="' + esc(course.id) + '">' + esc(course.code + " · " + course.title) + "</option>"
  ).join("");
  $("#assessment-course").innerHTML = $("#enroll-course").innerHTML;

  $("#admin-users").innerHTML =
    "<table><thead><tr><th>ID</th><th>User</th><th>Role</th><th>Status</th></tr></thead><tbody>" +
    state.adminUsers.map(
      (user) =>
        "<tr><td>" + esc(user.id) + "</td><td><strong>" +
        esc(user.full_name) + "</strong><div class=\"muted\">" +
        esc(user.username) + "</div></td><td>" +
        badge(user.role) + "</td><td>" +
        (user.active ? badge("RECORDED") : badge("MISSING")) +
        "</td></tr>"
    ).join("") +
    "</tbody></table>";

  $("#admin-courses").innerHTML =
    "<table><thead><tr><th>Course</th><th>Lecturer</th><th>Students</th><th>Assessments</th></tr></thead><tbody>" +
    state.adminCourses.map(
      (course) =>
        "<tr><td><strong>" + esc(course.code) + "</strong><div class=\"muted\">" +
        esc(course.title) + "</div></td><td>" +
        esc(course.lecturer_name || "Unassigned") + "</td><td>" +
        esc(course.students) + "</td><td>" +
        esc(course.assessments) + "</td></tr>"
    ).join("") +
    "</tbody></table>";
}

async function previewBatch() {
  const assessmentId = $("#lecturer-assessment").value;
  const csvText = $("#marks-csv").value.trim();
  if (!assessmentId || !csvText) {
    toast("Choose an assessment and provide CSV data.", "error");
    return null;
  }
  try {
    const result = await api("/api/lecturer/batches/preview", {
      method: "POST",
      body: JSON.stringify({ assessment_id: assessmentId, csv: csvText })
    });
    const errors = result.errors.length
      ? "<ul>" + result.errors.map((error) => "<li>" + esc(error) + "</li>").join("") + "</ul>"
      : "<p>Validation passed.</p>";
    $("#batch-preview").classList.remove("hidden");
    $("#batch-preview").innerHTML =
      "<strong>" +
      esc(result.course + " · " + result.assessment) +
      "</strong><p class=\"muted\">" +
      esc(result.submitted_count) +
      " submitted · " +
      esc(result.missing_count) +
      " missing · " +
      esc(result.enrolled_count) +
      " enrolled</p>" +
      errors;
    return result;
  } catch (error) {
    toast(error.message, "error");
    return null;
  }
}

async function submitBatch() {
  const preview = await previewBatch();
  if (!preview || !preview.valid) {
    toast("Fix validation errors before submitting.", "error");
    return;
  }
  if (!window.confirm("Submit this batch? Missing students will be recorded as missing marks.")) return;

  try {
    const result = await api("/api/lecturer/batches/submit", {
      method: "POST",
      body: JSON.stringify({
        assessment_id: $("#lecturer-assessment").value,
        csv: $("#marks-csv").value.trim()
      })
    });
    toast(
      result.chain_state === "LOCAL_ONLY"
        ? "Batch submitted locally. Chain is disabled."
        : "Batch submitted and committed on-chain."
    );
    $("#marks-csv").value = "";
    $("#batch-preview").classList.add("hidden");
    await loadLecturer();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
    await loadLecturer();
  }
}

function openAuditForBatch(batchId) {
  $("#audit-batch").innerHTML = '<option value="' + esc(batchId) + '">Selected batch</option>';
  showView("audit");
  loadAudit(batchId);
}

async function loadAudit(batchId) {
  try {
    const data = await api("/api/audit/batch/" + encodeURIComponent(batchId));
    $("#audit-batch").dataset.selected = batchId;
    const events = data.events
      .map(
        (event) =>
          '<div class="timeline-item"><strong>' +
          esc(event.action) +
          "</strong><span>" +
          esc(event.actor_name || "system") +
          "</span><small>" +
          esc(event.created_at) +
          "</small></div>"
      )
      .join("");
    const revisions = data.revisions
      .map(
        (revision) =>
          '<div class="timeline-item"><strong>Revision ' +
          esc(revision.revision) +
          " · " +
          esc(revision.kind) +
          '</strong><span>Actor: ' +
          esc(revision.actor_name) +
          " · " +
          badge(revision.chain_state) +
          '</span><small>' +
          esc(revision.created_at) +
          "</small></div>"
      )
      .join("");
    const history =
      data.mark_history.length === 0
        ? '<p class="muted">No mark amendments recorded for this batch.</p>'
        : data.mark_history
            .map(
              (entry) =>
                '<div class="timeline-item"><strong>' +
                esc(entry.action) +
                '</strong><span>Student ID ' +
                esc(entry.student_id) +
                ": " +
                esc(entry.old_mark ?? "—") +
                " → " +
                esc(entry.new_mark ?? "—") +
                " · " +
                esc(entry.actor_name) +
                '</span><small>' +
                esc(entry.reason || "") +
                "</small></div>"
            )
            .join("");

    $("#audit-result").innerHTML =
      '<div class="card"><p class="eyebrow">BATCH</p><h3>' +
      esc(data.batch.course + " · " + data.batch.assessment) +
      "</h3><p class=\"muted\">Status " +
      badge(data.batch.status) +
      " · revision " +
      esc(data.batch.revision) +
      " · chain " +
      badge(data.batch.chain_state) +
      '</p><div class="hash-box"><div class="mini-label">CURRENT COMMITMENT</div><code>' +
      esc(data.batch.marks_hash) +
      "</code></div></div>" +
      '<div class="card"><p class="eyebrow">REVISIONS</p><div class="timeline">' +
      revisions +
      '</div></div><div class="card"><p class="eyebrow">MARK HISTORY</p><div class="timeline">' +
      history +
      '</div></div><div class="card"><p class="eyebrow">APPLICATION EVENTS</p><div class="timeline">' +
      events +
      "</div></div>";
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadAuditSelector() {
  let batches = state.batches || [];
  if (batches.length === 0 && state.user.role === "lecturer") {
    const data = await api("/api/lecturer/batches");
    batches = data.batches;
  }
  if (batches.length === 0 && state.user.role === "reviewer") {
    const data = await api("/api/reviewer/batches");
    batches = data.batches;
  }
  if (batches.length === 0 && state.user.role === "admin") {
    const data = await api("/api/admin/batches");
    batches = data.batches;
  }
  if (batches.length === 0) {
    const marks = await api("/api/student/marks").catch(() => ({ marks: [] }));
    batches = marks.marks.filter((item) => item.batch_id).map((item) => ({
      id: item.batch_id,
      course: item.course,
      assessment: item.assessment
    }));
  }
  $("#audit-batch").innerHTML = batches.length
    ? batches.map(
        (batch) =>
          '<option value="' + esc(batch.id) + '">' +
          esc((batch.course || "") + " · " + (batch.assessment || "")) +
          "</option>"
      ).join("")
    : '<option value="">No batches available</option>';
}

async function loadCurrentView() {
  try {
    if (state.user.role === "student") await loadStudent();
    if (state.user.role === "lecturer") await loadLecturer();
    if (state.user.role === "reviewer") await loadReviewer();
    if (state.user.role === "admin") await loadAdmin();
    if (state.navView === "audit") await loadAuditSelector();
  } catch (error) {
    if (error.status === 401) {
      await boot();
      return;
    }
    toast(error.message, "error");
  }
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#login-username").value.trim(),
        password: $("#login-password").value
      })
    });
    $("#login-password").value = "";
    $("#login-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await loadDashboard();
    await loadCurrentView();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#logout-button").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  location.reload();
});

$("#marks-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (file) $("#marks-csv").value = await file.text();
});

$("#preview-batch").addEventListener("click", previewBatch);
$("#submit-batch").addEventListener("click", submitBatch);

$("#load-audit").addEventListener("click", () => {
  const batchId = $("#audit-batch").value;
  if (batchId) loadAudit(batchId);
});

$("#reconcile-audit").addEventListener("click", async () => {
  const batchId = $("#audit-batch").value;
  if (!batchId || !["reviewer", "admin"].includes(state.user.role)) {
    toast("Only reviewers/admins can reconcile with the chain.", "error");
    return;
  }
  const endpoint = "/api/admin/reconcile/" + encodeURIComponent(batchId);
  try {
    const result = await api(endpoint);
    toast(result.status === "MATCH" ? "Local batch matches the chain." : "Reconciliation found a mismatch or local-only mode.", result.status === "MATCH" ? "success" : "error");
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#create-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries()))
    });
    event.target.reset();
    toast("User created.");
    await loadAdmin();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#create-course-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const data = Object.fromEntries(form.entries());
  data.lecturer_id = Number(data.lecturer_id);
  try {
    await api("/api/admin/courses", {
      method: "POST",
      body: JSON.stringify(data)
    });
    event.target.reset();
    toast("Course created.");
    await loadAdmin();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#enroll-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const ids = String(form.get("student_ids"))
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value));
  try {
    await api("/api/admin/courses/" + encodeURIComponent(form.get("course_id")) + "/enroll", {
      method: "POST",
      body: JSON.stringify({ student_ids: ids })
    });
    toast("Students enrolled.");
    await loadAdmin();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#create-assessment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const data = Object.fromEntries(form.entries());
  data.max_mark = Number(data.max_mark);
  try {
    await api("/api/admin/courses/" + encodeURIComponent(form.get("course_id")) + "/assessments", {
      method: "POST",
      body: JSON.stringify({ name: data.name, max_mark: data.max_mark })
    });
    event.target.reset();
    toast("Assessment created.");
    await loadAdmin();
  } catch (error) {
    toast(error.message, "error");
  }
});

document.querySelectorAll("[data-refresh]").forEach((button) => {
  button.addEventListener("click", async () => {
    await loadDashboard();
    await loadCurrentView();
    toast("Refreshed.");
  });
});

async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;
    $("#login-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await loadDashboard();
    await loadCurrentView();
  } catch {
    $("#login-screen").classList.remove("hidden");
    $("#app-shell").classList.add("hidden");
  }
}

boot();
