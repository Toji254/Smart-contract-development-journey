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
let bulkActivationCredentials = [];

const $ = (selector) => document.querySelector(selector);

// ── Theme ────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("marktrail-theme");
  const theme = saved || "light";
  document.documentElement.setAttribute("data-theme", theme);
  updateThemeIcon(theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("marktrail-theme", next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const sun = $("#theme-icon-sun");
  const moon = $("#theme-icon-moon");
  if (sun && moon) {
    sun.classList.toggle("hidden", theme === "dark");
    moon.classList.toggle("hidden", theme !== "dark");
  }
}

initTheme();
$("#theme-toggle").addEventListener("click", toggleTheme);

// ── Utils ────────────────────────────────────────────────────
function toast(message, type = "success") {
  const node = document.createElement("div");
  node.className = "toast " + type;
  node.textContent = message;
  $("#toast-region").appendChild(node);
  setTimeout(() => node.remove(), 4000);
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
    VERIFIED: ["success", "Department approved"],
    SUBMITTED: ["warning", "Awaiting review"],
    AMENDED: ["info", "Amended / review needed"],
    OPEN: ["warning", "Open"],
    PENDING_REVIEW: ["info", "Pending review"],
    RESOLVED: ["success", "Resolved"],
    REJECTED: ["warning", "Rejected"],
    MISSING: ["warning", "Missing"],
    OVERDUE: ["warning", "Overdue"],
    AWAITING_PUBLICATION: ["info", "Awaiting publication"],
    RECORDED: ["success", "Recorded"],
    NO_MARK: ["info", "No mark awarded"],
    CONFIRMED: ["success", "Record checked"],
    LOCAL_ONLY: ["muted", "History saved"],
    ERROR: ["error", "Needs attention"],
    PENDING: ["warning", "Check pending"]
  };
  const stages = {
    DEPARTMENT_REVIEW: ["warning", "Awaiting department review"],
    EXAM_OFFICE: ["info", "At exam office"],
    PORTAL_IMPORT: ["info", "Awaiting portal import"],
    PUBLISHED: ["success", "Published"],
    NOT_SUBMITTED: ["muted", "Not submitted"]
  };
  const entry = map[value] || stages[value] || ["muted", value || "Unknown"];
  return '<span class="badge ' + entry[0] + '">' + esc(entry[1]) + "</span>";
}

// ── Navigation ───────────────────────────────────────────────
function showView(view) {
  state.navView = view;
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.add("hidden"));
  const role = state.user.role;
  const panelMap = {
    student: { home: "student-panel", marks: "student-panel", reports: "student-panel", audit: "audit-panel" },
    lecturer: { home: "lecturer-panel", batches: "lecturer-panel", reports: "lecturer-panel", audit: "audit-panel" },
    reviewer: { home: "reviewer-panel", verify: "reviewer-panel", audit: "audit-panel" },
    exam_office: { home: "exam-office-panel", process: "exam-office-panel", audit: "audit-panel" },
    portal_operator: { home: "portal-operator-panel", import: "portal-operator-panel", audit: "audit-panel" },
    admin: { home: "admin-panel", setup: "admin-panel", audit: "audit-panel" }
  };
  const id = panelMap[role]?.[view] || panelMap[role]?.home;
  if (id) {
    const panel = $("#" + id);
    panel.classList.remove("hidden");
    panel.querySelectorAll("[data-role-view]").forEach((section) => {
      section.classList.toggle("hidden", section.dataset.roleView !== view);
    });
  }
  $("#reconcile-audit").classList.toggle(
    "hidden",
    role !== "admin" || view !== "audit"
  );
  $("#dashboard-stats").classList.toggle("hidden", view !== "home");
  $("#chain-indicator").classList.toggle(
    "hidden",
    role !== "admin" || view !== "home"
  );
  document.querySelectorAll("#nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  updatePageHeading(view);
}

function updatePageHeading(view) {
  const titles = {
    home: ["Dashboard", "The current state of your marks workflow."],
    marks: ["My marks", "See what's published and what still needs attention."],
    reports: ["My reports", "See updates on the missing marks you reported."],
    batches: ["Upload and batches", "Upload marks and follow their progress."],
    verify: ["Review batches", "Check submitted marks and approve them for processing."],
    process: ["Process batches", "Record exam-office processing."],
    import: ["Publish marks", "Make processed marks available to students."],
    setup: ["Institution setup", "Users, courses, rosters, and assessments."],
    audit: ["Batch history", "Follow the handoffs and see what changed."]
  };
  const item = titles[view] || titles.home;
  $("#page-title").textContent = item[0];
  $("#page-subtitle").textContent = item[1];
}

function buildNav() {
  const role = state.user.role;
  const views = {
    student: [["home", "Dashboard"], ["marks", "My marks"], ["reports", "My reports"], ["audit", "History"]],
    lecturer: [["home", "Dashboard"], ["batches", "Upload & batches"], ["reports", "Issues"], ["audit", "History"]],
    reviewer: [["home", "Dashboard"], ["verify", "Review batches"], ["audit", "History"]],
    exam_office: [["home", "Dashboard"], ["process", "Process batches"], ["audit", "History"]],
    portal_operator: [["home", "Dashboard"], ["import", "Publish marks"], ["audit", "History"]],
    admin: [["home", "Dashboard"], ["setup", "Setup"], ["audit", "History"]]
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

// ── Dashboard stats ──────────────────────────────────────────
function renderStats(dashboard) {
  const counts = dashboard.counts || {};
  const role = dashboard.user.role;
  const roleStats = {
    student: [["Assessments", counts.assessments], ["Missing", counts.missing]],
    lecturer: [["Batches", counts.batches], ["Open issues", counts.issues]],
    reviewer: [["Pending verification", counts.pending_verification]],
    exam_office: [["Pending processing", counts.pending_processing]],
    portal_operator: [["Pending import", counts.pending_import]]
  };
  const entries = roleStats[role] || [
    ["Users", counts.users],
    ["Courses", counts.courses],
    ["Assessments", counts.assessments],
    ["Open issues", counts.issues]
  ];

  $("#dashboard-stats").innerHTML = entries
    .map(([label, value]) => '<div class="stat"><strong>' + esc(value) + '</strong><span>' + esc(label) + "</span></div>")
    .join("");

  const chain = dashboard.chain || {};
  const indicator = $("#chain-indicator");
  indicator.textContent = chain.enabled ? "Record checks active" : "Records saved locally";
  indicator.className = "pill " + (chain.enabled ? "success" : "neutral");
  if (chain.error) {
    indicator.textContent = "Record checks need attention";
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

// ── Student ──────────────────────────────────────────────────
async function loadStudent() {
  const [marksData, reportsData, notificationData] = await Promise.all([
    api("/api/student/marks"),
    api("/api/student/reports"),
    api("/api/student/notifications")
  ]);
  const notifications = notificationData.notifications;
  const unreadCount = notifications.filter((item) => !item.read_at).length;
  $("#student-notifications").innerHTML =
    '<div class="section-head compact"><div><p class="eyebrow">UPDATES</p><h2>Notifications' +
    (unreadCount ? " · " + unreadCount + " new" : "") +
    "</h2></div></div>" +
    (notifications.length
      ? notifications.map((item) =>
          '<div class="issue notification' +
          (item.read_at ? " read" : "") +
          '"><div class="issue-top"><div><strong>' +
          esc(item.title) +
          '</strong><p class="muted">' +
          esc(item.body) +
          '</p><small>' +
          esc(item.created_at) +
          "</small></div>" +
          (!item.read_at
            ? '<button class="button ghost" data-notification-read="' + esc(item.id) + '">Mark read</button>'
            : "") +
          "</div></div>"
        ).join("")
      : '<div class="card"><p class="muted">No notifications yet.</p></div>');

  $("#student-notifications").querySelectorAll("[data-notification-read]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/student/notifications/" + encodeURIComponent(button.dataset.notificationRead) + "/read", { method: "POST" });
        await loadStudent();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  // Group marks by course
  const byCourse = {};
  for (const mark of marksData.marks) {
    const key = mark.course;
    if (!byCourse[key]) byCourse[key] = { title: mark.course_title, marks: [] };
    byCourse[key].marks.push(mark);
  }

  let marksHtml = "";
  for (const [code, group] of Object.entries(byCourse)) {
    marksHtml += '<div class="card"><h3>' + esc(code) + ' — ' + esc(group.title) + '</h3>';
    marksHtml += "<table><thead><tr><th>Assessment</th><th>Mark</th><th>Status</th><th>Pipeline</th><th></th></tr></thead><tbody>";
    for (const mark of group.marks) {
      const action =
        mark.status === "MISSING" && mark.batch_status === "VERIFIED" && mark.pipeline_stage === "PUBLISHED"
          ? '<button class="button secondary" data-report="' + esc(mark.assessment_id) + '">Report missing</button>'
          : "";
      const display =
        mark.mark === null ||
        ["MISSING", "NO_MARK", "AWAITING_PUBLICATION", "NOT_SUBMITTED", "OVERDUE"].includes(mark.status)
          ? "—"
          : Number(mark.mark).toFixed(mark.mark % 1 ? 2 : 0) + "/" + mark.max_mark;
      const deadline = mark.submission_deadline
        ? '<br><small class="muted">Due: ' + esc(mark.submission_deadline) + '</small>'
        : "";
      marksHtml +=
        "<tr><td>" + esc(mark.assessment) + deadline +
        "</td><td><strong>" + display +
        "</strong></td><td>" + badge(mark.status) +
        "</td><td>" + badge(mark.pipeline_stage) +
        "</td><td>" + action + "</td></tr>";
    }
    marksHtml += "</tbody></table></div>";
  }
  if (!marksHtml) marksHtml = '<div class="card"><p class="muted">No assessments found.</p></div>';
  $("#student-marks").innerHTML = marksHtml;

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

// ── Lecturer ─────────────────────────────────────────────────
async function loadLecturer() {
  const [assessmentsData, batchesData, reportsData] = await Promise.all([
    api("/api/lecturer/assessments"),
    api("/api/lecturer/batches"),
    api("/api/lecturer/reports")
  ]);

  state.assessments = assessmentsData.assessments;
  state.batches = batchesData.batches;
  state.reports = reportsData.reports;

  const availableAssessments = state.assessments.filter((assessment) => !assessment.batch_id);
  $("#lecturer-assessment").innerHTML = availableAssessments.length
    ? '<option value="">Choose an unsubmitted assessment</option>' +
      availableAssessments
        .map((assessment) =>
          '<option value="' + esc(assessment.id) + '">' +
          esc(assessment.course + " · " + assessment.name) +
          "</option>"
        )
        .join("")
    : '<option value="">No unsubmitted assessments</option>';
  $("#lecturer-assessment").disabled = availableAssessments.length === 0;
  $("#assessment-help").textContent = availableAssessments.length
    ? "Choose an assessment that has not been submitted yet. To correct a published batch, use the missing-mark issue workflow."
    : "There are no unsubmitted assessments for your courses. Ask an administrator to create an assessment before uploading marks.";
  $("#preview-batch").disabled = availableAssessments.length === 0;
  $("#submit-batch").disabled = availableAssessments.length === 0;

  // Render reports with inline forms instead of window.prompt
  $("#lecturer-reports").innerHTML =
    state.reports.length === 0
      ? '<div class="card"><p class="muted">No missing-mark issues.</p></div>'
      : state.reports
          .map((report) => {
            let actions = "";
            if (report.status === "OPEN") {
              actions =
                '<div class="resolve-form" id="resolve-' + esc(report.id) + '">' +
                '<label>Mark <input type="number" step="0.01" min="0" class="resolve-mark" placeholder="e.g. 17"></label>' +
                '<label>Note <input type="text" class="resolve-note" placeholder="Missing mark restored" value="Missing mark restored."></label>' +
                '<div class="actions">' +
                '<button class="button primary" data-resolve-mark="' + esc(report.id) + '">Submit mark</button>' +
                '<button class="button secondary" data-no-mark="' + esc(report.id) + '">No mark awarded</button>' +
                '<button class="button ghost" data-reject-report="' + esc(report.id) + '">Reject report</button>' +
                '</div></div>';
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

  // Bind inline resolution forms
  $("#lecturer-reports").querySelectorAll("[data-resolve-mark]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = button.closest(".resolve-form");
      const markInput = form.querySelector(".resolve-mark");
      const noteInput = form.querySelector(".resolve-note");
      const mark = Number(markInput.value);
      if (!Number.isFinite(mark) || mark < 0) {
        toast("Enter a valid numeric mark.", "error");
        return;
      }
      resolveReport(button.dataset.resolveMark, "MARK_ENTERED", mark, noteInput.value || "Missing mark restored.");
    });
  });
  $("#lecturer-reports").querySelectorAll("[data-no-mark]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = button.closest(".resolve-form");
      const noteInput = form.querySelector(".resolve-note");
      resolveReport(button.dataset.noMark, "NO_MARK_AWARDED", null, noteInput.value || "Student did not have an awarded mark.");
    });
  });
  $("#lecturer-reports").querySelectorAll("[data-reject-report]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = button.closest(".resolve-form");
      const noteInput = form.querySelector(".resolve-note");
      if (!noteInput.value.trim()) {
        toast("Please provide a reason for rejection.", "error");
        return;
      }
      rejectReport(button.dataset.rejectReport, noteInput.value);
    });
  });

  $("#lecturer-batches").innerHTML =
    state.batches.length === 0
      ? '<div class="card"><p class="muted">No submitted batches.</p></div>'
      : "<table><thead><tr><th>Course</th><th>Assessment</th><th>Status</th><th>Record check</th><th>Actions</th></tr></thead><tbody>" +
        state.batches
          .map(
            (batch) =>
              "<tr><td>" +
              esc(batch.course) +
              "</td><td>" +
              esc(batch.assessment) +
              "</td><td>" +
              badge(batch.pipeline_stage) +
              "</td><td>" +
              badge(batch.chain_state) +
              '</td><td><div class="actions" style="margin-top:0"><button class="button secondary" data-audit-batch="' +
              esc(batch.id) +
              '">View history</button>' +
              "</div></td></tr>"
          )
          .join("") +
        "</tbody></table>";

  $("#lecturer-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

async function resolveReport(reportId, resolutionType, mark, note) {
  try {
    await api("/api/lecturer/reports/" + encodeURIComponent(reportId) + "/resolve", {
      method: "POST",
      body: JSON.stringify({
        resolution_type: resolutionType,
        mark,
        note
      })
    });
    toast("Resolution recorded. Reviewer, exam office, and portal steps are still required.");
    await loadLecturer();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
    if (error.status === 502) {
      try {
        await loadLecturer();
        await loadDashboard();
      } catch (refreshError) {
        toast("The saved resolution could not be refreshed: " + refreshError.message, "error");
      }
    }
  }
}

async function rejectReport(reportId, reason) {
  try {
    await api("/api/lecturer/reports/" + encodeURIComponent(reportId) + "/reject", {
      method: "POST",
      body: JSON.stringify({ reason })
    });
    toast("Report rejected. The student can report again if the mark is still missing.");
    await loadLecturer();
  } catch (error) {
    toast(error.message, "error");
  }
}

// ── Reviewer ─────────────────────────────────────────────────
async function loadReviewer() {
  const data = await api("/api/reviewer/batches");
  state.batches = data.batches;
  const waiting = state.batches.filter(
    (batch) => batch.pipeline_stage === "DEPARTMENT_REVIEW"
  );

  $("#reviewer-batches").innerHTML =
    waiting.length === 0
      ? '<div class="card"><p class="muted">You are all caught up. No batches are waiting for your review.</p></div>'
      : waiting
          .map((batch) => {
            const canVerify = ["SUBMITTED", "AMENDED"].includes(batch.status) &&
              batch.pipeline_stage === "DEPARTMENT_REVIEW" &&
              ["CONFIRMED", "LOCAL_ONLY"].includes(batch.chain_state);
            const action = canVerify
              ? '<button class="button primary" data-verify="' + esc(batch.id) + '">Approve for exam office</button>'
              : "";
            const needsAdmin = ["ERROR", "PENDING"].includes(batch.chain_state);
            return (
              '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
              esc(batch.course + " · " + batch.assessment) +
              '</div><div class="muted">' +
              esc(batch.lecturer_name) +
              " · " +
              esc(batch.student_count) +
              ' students</div></div>' +
              badge(batch.status) +
              '</div><p class="muted">Handoff: ' +
              badge(batch.pipeline_stage) +
              " · Record check: " +
              badge(batch.chain_state) +
              '</p><div class="actions">' +
              action +
              (needsAdmin
                ? '<span class="muted">This batch needs administrator attention before it can be approved.</span>'
                : "") +
              '<button class="button secondary" data-audit-batch="' +
              esc(batch.id) +
              '">View history</button></div></div>'
            );
          })
          .join("");

  $("#reviewer-batches").querySelectorAll("[data-verify]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/reviewer/batches/" + encodeURIComponent(button.dataset.verify) + "/verify", { method: "POST" });
        toast("Department review complete. Batch sent to the exam office.");
        await loadReviewer();
        await loadDashboard();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  $("#reviewer-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

// ── Exam Office ──────────────────────────────────────────────
async function loadExamOffice() {
  const data = await api("/api/exam-office/batches");
  $("#exam-office-batches").innerHTML = data.batches.length
    ? data.batches.map((batch) =>
        '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
        esc(batch.course + " · " + batch.assessment) +
        '</div><div class="muted">' +
        esc(batch.lecturer_name + " · " + batch.student_count + " students") +
        "</div></div>" +
        badge(batch.pipeline_stage) +
        '</div><div class="actions"><button class="button primary" data-process-batch="' +
        esc(batch.id) +
        '">Mark processed</button><button class="button secondary" data-audit-batch="' +
        esc(batch.id) +
        '">View history</button></div></div>'
      ).join("")
    : '<div class="card"><p class="muted">No batches waiting for exam-office processing.</p></div>';

  $("#exam-office-batches").querySelectorAll("[data-process-batch]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/exam-office/batches/" + encodeURIComponent(button.dataset.processBatch) + "/process", { method: "POST" });
        toast("Processing recorded. The batch is now ready for portal import.");
        await loadExamOffice();
        await loadDashboard();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });
  $("#exam-office-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

// ── Portal Operator ──────────────────────────────────────────
async function loadPortalOperator() {
  const data = await api("/api/portal/batches");
  $("#portal-batches").innerHTML = data.batches.length
    ? data.batches.map((batch) =>
        '<div class="issue"><div class="issue-top"><div><div class="issue-title">' +
        esc(batch.course + " · " + batch.assessment) +
        '</div><div class="muted">' +
        esc(batch.lecturer_name + " · " + batch.student_count + " students") +
        "</div></div>" +
        badge(batch.pipeline_stage) +
        '</div><div class="actions"><button class="button primary" data-publish-batch="' +
        esc(batch.id) +
        '">Import and publish</button><button class="button secondary" data-audit-batch="' +
        esc(batch.id) +
        '">View history</button></div></div>'
      ).join("")
    : '<div class="card"><p class="muted">No batches waiting for portal import.</p></div>';

  $("#portal-batches").querySelectorAll("[data-publish-batch]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Import and publish these marks to students?")) return;
      try {
        await api("/api/portal/batches/" + encodeURIComponent(button.dataset.publishBatch) + "/publish", { method: "POST" });
        toast("Marks imported and published to students.");
        await loadPortalOperator();
        await loadDashboard();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });
  $("#portal-batches").querySelectorAll("[data-audit-batch]").forEach((button) => {
    button.addEventListener("click", () => openAuditForBatch(button.dataset.auditBatch));
  });
}

// ── Admin ────────────────────────────────────────────────────
async function loadAdmin() {
  const [users, coursesData, batches] = await Promise.all([
    api("/api/admin/users"),
    api("/api/admin/courses"),
    api("/api/admin/batches")
  ]);
  state.adminUsers = users.users;
  state.adminCourses = coursesData.courses;
  state.adminBatches = batches.batches;

  const today = new Date().toISOString().slice(0, 10);
  const lecturers = state.adminUsers.filter(
    (user) =>
      user.role === "lecturer" &&
      user.active &&
      (!user.access_until || user.access_until >= today)
  );
  $("#course-lecturer").innerHTML = lecturers.map(
    (user) => '<option value="' + esc(user.id) + '">' + esc(user.full_name + " · " + user.username) + "</option>"
  ).join("");

  const courses = state.adminCourses;
  $("#enroll-course").innerHTML = courses.map(
    (course) => '<option value="' + esc(course.id) + '">' + esc(course.code + " · " + course.title) + "</option>"
  ).join("");
  $("#assessment-course").innerHTML = $("#enroll-course").innerHTML;
  $("#bulk-enroll-course").innerHTML = $("#enroll-course").innerHTML;

  $("#admin-users").innerHTML =
    "<table><thead><tr><th>User</th><th>Reg #</th><th>Role</th><th>Account access</th><th>Manage</th></tr></thead><tbody>" +
    state.adminUsers.map(
      (user) => {
        const expired = user.access_until && user.access_until < today;
        const status = !user.active
          ? '<span class="badge muted">Disabled</span>'
          : expired
            ? '<span class="badge warning">Expired</span>'
            : '<span class="badge success">Enabled</span>';
        return (
        "<tr><td><strong>" +
        esc(user.full_name) + '</strong><div class="muted">' +
        esc(user.username) + "</div></td><td>" +
        esc(user.reg_number || "—") + "</td><td>" +
        badge(user.role) + "</td><td>" +
        status + '<div class="muted">' +
        (user.access_until ? "Through " + esc(user.access_until) : "No scheduled end date") +
        '</div></td><td><form class="user-access-form" data-user-id="' + esc(user.id) + '">' +
        '<label class="user-access-enabled"><input type="checkbox" name="active"' + (user.active ? " checked" : "") +
        '> Account enabled</label>' +
        '<label>Access through<input name="access_until" type="date" value="' +
        esc(user.access_until || "") + '"></label>' +
        '<button class="button secondary">Save access</button></form></td></tr>'
        );
      }
    ).join("") +
    "</tbody></table>";
  $("#admin-users").querySelectorAll(".user-access-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      try {
        await api("/api/admin/users/" + encodeURIComponent(form.dataset.userId) + "/access", {
          method: "POST",
          body: JSON.stringify({
            active: values.has("active"),
            access_until: values.get("access_until")
          })
        });
        toast("Account access updated.");
        await loadAdmin();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  $("#admin-courses").innerHTML =
    "<table><thead><tr><th>Course</th><th>Lecturer</th><th>Students</th><th>Assessments</th></tr></thead><tbody>" +
    state.adminCourses.map(
      (course) =>
        "<tr><td><strong>" + esc(course.code) + '</strong><div class="muted">' +
        esc(course.title) + "</div></td><td>" +
        esc(course.lecturer_name || "Unassigned") + "</td><td>" +
        esc(course.students) + "</td><td>" +
        esc(course.assessments) + "</td></tr>"
    ).join("") +
    "</tbody></table>";

  const batchesContainer = $("#admin-batches");
  if (batchesContainer) {
    batchesContainer.innerHTML =
      state.adminBatches.length === 0
        ? '<div class="card"><p class="muted">No mark batches created yet.</p></div>'
        : "<table><thead><tr><th>Course · Assessment</th><th>Lecturer</th><th>Students</th><th>Current step</th><th>Update check</th><th>Actions</th></tr></thead><tbody>" +
          state.adminBatches.map(
            (b) =>
              "<tr><td><strong>" + esc(b.course + " · " + b.assessment) + '</strong><div class="muted"><code>' + esc(b.id.slice(0, 10)) + '…</code></div></td>' +
              "<td>" + esc(b.lecturer_name) + "</td>" +
              "<td>" + esc(b.student_count) + "</td>" +
              "<td>" + badge(b.pipeline_stage) + "</td>" +
              "<td>" + badge(b.chain_state) + "</td>" +
              '<td><div class="actions" style="margin-top:0"><button class="button secondary" data-audit-batch="' + esc(b.id) + '">View history</button>' +
              (b.chain_state === "ERROR"
                ? ' <button class="button secondary" data-admin-retry="' + esc(b.id) + '">Retry update</button>'
                : "") +
              "</div></td></tr>"
          ).join("") +
          "</tbody></table>";

    batchesContainer.querySelectorAll("[data-audit-batch]").forEach((btn) => {
      btn.addEventListener("click", () => openAuditForBatch(btn.dataset.auditBatch));
    });
    batchesContainer.querySelectorAll("[data-admin-retry]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api("/api/admin/batches/" + encodeURIComponent(btn.dataset.adminRetry) + "/retry-chain", {
            method: "POST"
          });
          toast("Record update retried successfully.");
          await loadAdmin();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  }

  const recoverBtn = $("#admin-recover-chain");
  if (recoverBtn && !recoverBtn.dataset.bound) {
    recoverBtn.dataset.bound = "1";
    recoverBtn.addEventListener("click", async () => {
      try {
        const res = await api("/api/admin/batches/recover", { method: "POST" });
        toast("Recovery run complete: " + res.recovered + " recovered, " + res.errors + " errors.");
        await loadAdmin();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }
}

// ── Batch preview/submit ─────────────────────────────────────
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
      '</strong><p class="muted">' +
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
    await api("/api/lecturer/batches/submit", {
      method: "POST",
      body: JSON.stringify({
        assessment_id: $("#lecturer-assessment").value,
        csv: $("#marks-csv").value.trim()
      })
    });
    toast("Batch submitted. It is now waiting for department review.");
    $("#marks-csv").value = "";
    $("#batch-preview").classList.add("hidden");
    await loadLecturer();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
    await loadLecturer();
  }
}

// ── Audit ────────────────────────────────────────────────────
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
          esc({
            BATCH_SUBMITTED: "Marks submitted",
            BATCH_AMENDED: "Marks updated",
            BATCH_VERIFIED: "Department approved",
            EXAM_OFFICE_PROCESSED: "Exam office processed",
            PORTAL_IMPORTED: "Marks published",
            MARKS_PUBLISHED: "Marks made available",
            REPORT_RESOLVED: "Missing-mark report resolved",
            REPORT_OPENED: "Missing-mark report opened"
          }[event.action] || "Record updated") +
          "</strong><span>" +
          esc(event.actor_name || "system") +
          "</span><small>" +
          esc(formatDateTime(event.created_at)) +
          "</small></div>"
      )
      .join("");
    const revisions = data.revisions
      .map(
        (revision) =>
          '<div class="timeline-item"><strong>' +
          (revision.kind === "AMENDMENT" ? "Marks corrected" : "Marks submitted") +
          " · Change " +
          esc(revision.revision) +
          '</strong><span>Handled by ' +
          esc(revision.actor_name) +
          '</span><small>' +
          esc(formatDateTime(revision.created_at)) +
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
                esc({
                  MARK_AMENDED: "Mark corrected",
                  REPORT_RESOLVED: "Missing-mark report resolved"
                }[entry.action] || "Mark updated") +
                '</strong><span>' +
                esc(entry.student_reg_number || entry.student_name || ("Student " + entry.student_id)) +
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
    const pipeline = data.pipeline.stages
      .map((stage) =>
        '<div class="timeline-item"><strong>' +
        esc(stage.owner) +
        " · " +
        (stage.completed_at ? "Done" : "In progress") +
        '</strong><span>' +
        (stage.completed_at
          ? "Completed " + esc(formatDateTime(stage.completed_at))
          : "Started " + esc(formatDateTime(stage.started_at))) +
        (stage.completed_by ? " · handled by " + esc(stage.completed_by) : "") +
        "</span></div>"
      )
      .join("");

    const integrityLabels = {
      CONFIRMED: "Record check complete",
      LOCAL_ONLY: "History saved",
      PENDING: "Record check pending",
      ERROR: "Record check needs administrator attention"
    };
    $("#audit-result").innerHTML =
      '<div class="card"><p class="eyebrow">BATCH</p><h3>' +
      esc(data.batch.course + " · " + data.batch.assessment) +
      '</h3><p class="muted">Current status ' +
      badge(data.batch.status) +
      " · " +
      esc(integrityLabels[data.batch.chain_state] || "Record status unavailable") +
      '</p><p class="muted">' +
      (data.pipeline.current_stage === "PUBLISHED"
        ? "<strong>Published to students</strong>"
        : "Currently with <strong>" +
          esc(data.pipeline.current_owner) +
          "</strong> · waiting " +
          esc(formatDuration(data.pipeline.waiting_seconds)) +
          (data.pipeline.waiting_since ? " since " + esc(data.pipeline.waiting_since) : "")) +
      '</p></div><div class="card"><p class="eyebrow">HANDOFFS</p><div class="timeline">' +
      (pipeline || '<p class="muted">No handoff events recorded yet.</p>') +
      '</div></div>' +
      '<div class="card"><p class="eyebrow">MARKS CHANGES</p><div class="timeline">' +
      revisions +
      '</div></div><div class="card"><p class="eyebrow">MARK HISTORY</p><div class="timeline">' +
      history +
      '</div></div><div class="card"><p class="eyebrow">ACTIVITY</p><div class="timeline">' +
      events +
      "</div></div>";
  } catch (error) {
    toast(error.message, "error");
  }
}

function formatDuration(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return days + "d " + hours + "h";
  if (hours) return hours + "h " + minutes + "m";
  return minutes + "m";
}

function formatDateTime(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
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
  if (batches.length === 0 && state.user.role === "exam_office") {
    const data = await api("/api/exam-office/batches");
    batches = data.batches;
  }
  if (batches.length === 0 && state.user.role === "portal_operator") {
    const data = await api("/api/portal/batches");
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

// ── View loader ──────────────────────────────────────────────
async function loadCurrentView() {
  try {
    if (state.user.role === "student") await loadStudent();
    if (state.user.role === "lecturer") await loadLecturer();
    if (state.user.role === "reviewer") await loadReviewer();
    if (state.user.role === "exam_office") await loadExamOffice();
    if (state.user.role === "portal_operator") await loadPortalOperator();
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

// ── Login ────────────────────────────────────────────────────
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#login-username").value.trim(),
        password: $("#login-password").value
      })
    });
    $("#login-password").value = "";

    if (result.must_change_password) {
      // Show password change screen
      $("#login-screen").classList.add("hidden");
      $("#password-change-screen").classList.remove("hidden");
      $("#pw-current").value = "";
      $("#pw-new").value = "";
      $("#pw-confirm").value = "";
      return;
    }

    $("#login-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await loadDashboard();
    await loadCurrentView();
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── Password change ──────────────────────────────────────────
$("#password-change-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const current = $("#pw-current").value;
  const newPw = $("#pw-new").value;
  const confirm = $("#pw-confirm").value;

  if (newPw !== confirm) {
    toast("New passwords do not match.", "error");
    return;
  }
  if (newPw.length < 8) {
    toast("New password must be at least 8 characters.", "error");
    return;
  }

  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: current,
        new_password: newPw
      })
    });
    toast("Password updated. You are now signed in.");
    $("#password-change-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await loadDashboard();
    await loadCurrentView();
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── Logout ───────────────────────────────────────────────────
$("#logout-button").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  location.reload();
});

// ── File input ───────────────────────────────────────────────
$("#marks-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (file) $("#marks-csv").value = await file.text();
});

$("#preview-batch").addEventListener("click", previewBatch);
$("#submit-batch").addEventListener("click", submitBatch);

// ── Audit controls ───────────────────────────────────────────
$("#load-audit").addEventListener("click", () => {
  const batchId = $("#audit-batch").value;
  if (batchId) loadAudit(batchId);
});

$("#download-audit").addEventListener("click", () => {
  const batchId = $("#audit-batch").value || $("#audit-batch").dataset.selected;
  if (!batchId) {
    toast("Choose a batch first.", "error");
    return;
  }
  const link = document.createElement("a");
  link.href = "/api/audit/batch/" + encodeURIComponent(batchId) + "/report.csv";
  link.download = "marktrail-audit.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
});

$("#reconcile-audit").addEventListener("click", async () => {
  const batchId = $("#audit-batch").value;
  if (!batchId || state.user.role !== "admin") {
    toast("Only administrators can check record integrity.", "error");
    return;
  }
  const endpoint = "/api/admin/reconcile/" + encodeURIComponent(batchId);
  try {
    const result = await api(endpoint);
    toast(result.status === "MATCH" ? "The saved record matches the verified copy." : "The saved record could not be verified. Review the batch status.", result.status === "MATCH" ? "success" : "error");
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── Admin: create user ───────────────────────────────────────
$("#create-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries()))
    });
    event.target.reset();
    $("#create-user-access-until").required = $("#create-user-role").value === "student";
    toast("User created.");
    await loadAdmin();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#create-user-role").addEventListener("change", () => {
  $("#create-user-access-until").required = $("#create-user-role").value === "student";
});

// ── Admin: create course ─────────────────────────────────────
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

// ── Admin: enroll ────────────────────────────────────────────
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

// ── Admin: bulk enroll CSV ───────────────────────────────────
$("#bulk-enroll-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  bulkActivationCredentials = [];
  $("#bulk-enroll-credentials").classList.add("hidden");
  $("#bulk-enroll-credentials-list").replaceChildren();
  try {
    const result = await api("/api/admin/courses/" + encodeURIComponent(form.get("course_id")) + "/bulk-enroll", {
      method: "POST",
      body: JSON.stringify({
        csv: form.get("csv"),
        access_until: form.get("access_until")
      })
    });
    toast("Enrolled " + result.enrolled + " students, created " + result.created + " accounts, skipped " + result.skipped + ".");
    bulkActivationCredentials = result.credentials || [];
    if (bulkActivationCredentials.length) {
      const rows = bulkActivationCredentials.map((credential) => {
        const row = document.createElement("tr");
        for (const value of [
          credential.full_name,
          credential.username,
          credential.activation_password
        ]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.appendChild(cell);
        }
        return row;
      });
      $("#bulk-enroll-credentials-list").replaceChildren(...rows);
      $("#bulk-enroll-credentials").classList.remove("hidden");
    }
    event.target.reset();
    await loadAdmin();
    await loadDashboard();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#download-bulk-enroll-credentials").addEventListener("click", () => {
  if (!bulkActivationCredentials.length) {
    toast("There are no new activation passwords to download.", "error");
    return;
  }
  const escapeCsv = (value) => '"' + String(value).replaceAll('"', '""') + '"';
  const rows = [
    ["full_name", "username", "activation_password"],
    ...bulkActivationCredentials.map((credential) => [
      credential.full_name,
      credential.username,
      credential.activation_password
    ])
  ];
  const content = rows.map((row) => row.map(escapeCsv).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "student-activation-credentials.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// ── Admin: create assessment ─────────────────────────────────
$("#create-assessment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const data = Object.fromEntries(form.entries());
  data.max_mark = Number(data.max_mark);
  // Convert datetime-local to ISO
  if (data.submission_deadline) {
    data.submission_deadline = new Date(data.submission_deadline).toISOString();
  }
  try {
    await api("/api/admin/courses/" + encodeURIComponent(form.get("course_id")) + "/assessments", {
      method: "POST",
      body: JSON.stringify({ name: data.name, max_mark: data.max_mark, submission_deadline: data.submission_deadline || null })
    });
    event.target.reset();
    toast("Assessment created.");
    await loadAdmin();
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── Refresh ──────────────────────────────────────────────────
document.querySelectorAll("[data-refresh]").forEach((button) => {
  button.addEventListener("click", async () => {
    await loadDashboard();
    await loadCurrentView();
    toast("Refreshed.");
  });
});

// ── Boot ─────────────────────────────────────────────────────
async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;

    if (me.must_change_password) {
      $("#login-screen").classList.add("hidden");
      $("#password-change-screen").classList.remove("hidden");
      return;
    }

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
