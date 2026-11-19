const state = {
  user: null,
  navView: "home",
  assessments: [],
  batches: [],
  reports: [],
  adminUsers: [],
  adminCourses: [],
  adminBatches: [],
  adminAssessments: [],
  staffCompleteness: null,
  senateBatches: [],
  evidenceAssessments: [],
  evidenceStaff: [],
  evidenceCases: [],
  evidenceAttachments: [],
  studentAttachments: [],
  evidenceSessions: [],
  evidenceSelectedAssessment: "",
  evidenceSelectedSession: "",
  evidenceDetail: null,
  evidenceDocumentAnalyses: {}
};
let bulkActivationCredentials = [];

const $ = (selector) => document.querySelector(selector);

// ── Theme ────────────────────────────────────────────────────
async function evidenceFileBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return btoa(binary);
}

async function uploadEvidenceAttachment(ownerType, ownerId, file) {
  if (!file) throw new Error("Choose an evidence file first.");
  if (file.size <= 0 || file.size > 10 * 1024 * 1024) {
    throw new Error("Evidence files must be larger than zero and no bigger than 10 MB.");
  }
  return api("/api/evidence/attachments", {
    method: "POST",
    body: JSON.stringify({
      owner_type: ownerType, owner_id: ownerId, filename: file.name,
      content_base64: await evidenceFileBase64(file)
    })
  });
}

function renderEvidenceDocumentAnalysis(attachmentId, analysis) {
  const suggestions = analysis.suggestions || {};
  const registrationNumbers = (suggestions.registration_number_candidates || []).join(", ");
  const dates = (suggestions.date_candidates || []).join(", ");
  const status = String(analysis.status || "UNKNOWN").replaceAll("_", " ");
  const textBlock = analysis.text
    ? '<details><summary>View extracted text (' + esc(analysis.extracted_character_count || analysis.text.length) + ' characters)</summary>' +
      '<pre>' + esc(analysis.text) + '</pre></details>'
    : "";
  return '<section class="evidence-document-analysis" data-document-analysis="' + esc(attachmentId) + '">' +
    '<div class="document-analysis-heading"><strong>Document intelligence · Human review required</strong>' +
    '<span class="badge warning">' + esc(status) + '</span></div>' +
    '<p><strong>Suggested document type:</strong> ' + esc(suggestions.suggested_document_type || "UNKNOWN") + '</p>' +
    '<p><strong>Possible registration references:</strong> ' + esc(registrationNumbers || "None detected") + '</p>' +
    '<p><strong>Possible dates:</strong> ' + esc(dates || "None detected") + '</p>' +
    '<p><strong>Keyword hits only:</strong> PRESENT ' + esc(suggestions.present_word_occurrences ?? 0) +
      ' · ABSENT ' + esc(suggestions.absent_word_occurrences ?? 0) + '</p>' +
    (analysis.warning ? '<p class="muted">' + esc(analysis.warning) + '</p>' : '') +
    '<p class="muted">OCR suggestions are not evidence of attendance, identity or marks. Compare with the original and locked roster. MarkTrail does not apply these values automatically.</p>' +
    textBlock + '</section>';
}

function renderEvidenceAttachmentList(items) {
  if (!items || !items.length) return '<p class="muted">No documents attached yet.</p>';
  return '<div class="evidence-attachment-list">' + items.map((item) => {
    const scanLabel = item.scan_status === "CLEAN"
      ? '<span class="badge success">Scanned · clean</span>'
      : item.scan_status === "INFECTED"
        ? '<span class="badge danger">Malware detected</span>'
        : item.scan_status === "CORRUPT"
          ? '<span class="badge danger">Integrity failure</span>'
          : '<span class="badge warning">Quarantined · scan required</span>';
    const download = item.scan_status === "CLEAN"
      ? '<a class="button secondary evidence-download" href="/api/evidence/attachments/' + encodeURIComponent(item.id) + '/download">Download</a>'
      : '<small class="muted">Download blocked until a clean scan succeeds.</small>';
    const canRescan = state.user?.role === "admin" &&
      ["QUARANTINED", "SCAN_ERROR", "INFECTED"].includes(item.scan_status);
    const rescan = canRescan
      ? '<button type="button" class="button secondary evidence-rescan" data-rescan-attachment="' + esc(item.id) + '">Rescan file</button>'
      : "";
    const canAnalyse = ["admin", "reviewer", "exam_office", "lecturer"].includes(state.user?.role) &&
      item.scan_status === "CLEAN";
    const analyse = canAnalyse
      ? '<button type="button" class="button secondary evidence-analyse" data-analyse-document="' + esc(item.id) + '">Extract / review</button>'
      : "";
    const history = (item.history || []).map((event) =>
      '<div class="attachment-history-event"><strong>' + esc(event.event_type.replaceAll("_", " ")) +
      '</strong><small>' + esc(event.actor_name) + ' · ' + esc(event.created_at) + '</small>' +
      (event.note ? '<span>' + esc(event.note) + '</span>' : '') + '</div>'
    ).join("");
    return '<div class="evidence-attachment-row" data-attachment-row="' + esc(item.id) + '"><div><strong>' + esc(item.filename) + '</strong>' +
      '<small class="muted">' + esc((item.byte_size / 1024).toFixed(1)) + ' KB · SHA-256 ' +
      esc(item.sha256.slice(0, 16)) + '… · ' + esc(item.uploaded_by_name || "Staff") + ' · ' +
      esc(item.created_at) + '</small>' +
      (history ? '<details class="attachment-history"><summary>File history (' + (item.history || []).length + ')</summary>' +
        '<div class="attachment-history-list">' + history + '</div></details>' : '') +
      '</div><div class="evidence-attachment-actions">' + scanLabel + download + rescan + analyse + '</div></div>' +
      (state.evidenceDocumentAnalyses[item.id]
        ? renderEvidenceDocumentAnalysis(item.id, state.evidenceDocumentAnalyses[item.id])
        : "");
  }).join("") + "</div>";
}

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
    PENDING: ["warning", "Check pending"],
    PRESENT: ["success", "Recorded present"],
    ABSENT: ["warning", "Recorded absent"],
    EXCUSED: ["info", "Excused"],
    CONTESTED: ["warning", "Disputed"],
    RECEIVED: ["success", "Script received"],
    HANDOFF_PENDING: ["warning", "Handover pending"],
    ASSIGNED: ["info", "Assigned to marker"],
    MARKED: ["success", "Marking completed"],
    FLAGGED: ["warning", "Needs review"],
    NOT_ENTERED: ["muted", "No mark entry recorded"],
    OPEN: ["warning", "Open case"],
    EVIDENCE_CLEARED: ["info", "Awaiting reviewer confirmation"],
    RESOLVED: ["success", "Resolved"],
    DISMISSED: ["muted", "Dismissed"],
    SENATE_APPROVAL: ["warning", "Awaiting Senate approval"],
    SENATE_DEFERRED: ["warning", "Deferred by Senate"],
    AWAITING_SENATE_APPROVAL: ["warning", "Awaiting Senate approval"],
    RELEASE_POLICY_UNCLASSIFIED: ["warning", "Release policy not classified"],
    DIRECT: ["success", "Direct release"],
    SENATE: ["info", "Senate approval required"],
    UNCLASSIFIED: ["warning", "Unclassified"],
    NOT_SUBMITTED: ["warning", "Not submitted"],
    POLICY_UNCLASSIFIED: ["warning", "Policy needs classification"],
    MISSING_IN_SUBMISSION: ["warning", "Missing in submitted batch"],
    AWAITING_DEPARTMENT_REVIEW: ["info", "Awaiting department review"],
    AWAITING_EXAM_OFFICE: ["info", "Awaiting exam office"],
    AWAITING_PORTAL_PUBLICATION: ["info", "Awaiting portal publication"],
    NO_ASSESSMENTS_CONFIGURED: ["warning", "No assessments configured"],
    CONFIGURATION_REQUIRED: ["warning", "Configuration required"],
    MISSING_COMPONENTS: ["error", "Missing component marks"],
    AWAITING_COMPONENTS: ["info", "Components still in progress"],
    OFFICIAL_NO_MARK_OUTCOME: ["warning", "Official no-mark outcome"],
    ALL_COMPONENTS_PUBLISHED: ["success", "All components published"]
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
    student: { home: "student-panel", marks: "student-panel", progress: "student-panel", reports: "student-panel", audit: "audit-panel" },
    lecturer: { home: "lecturer-panel", completeness: "lecturer-panel", batches: "lecturer-panel", reports: "lecturer-panel", evidence: "evidence-panel", audit: "audit-panel" },
    reviewer: { home: "reviewer-panel", verify: "reviewer-panel", evidence: "evidence-panel", audit: "audit-panel" },
    exam_office: { home: "exam-office-panel", process: "exam-office-panel", evidence: "evidence-panel", audit: "audit-panel" },
    portal_operator: { home: "portal-operator-panel", import: "portal-operator-panel", audit: "audit-panel" },
    senate_office: { home: "senate-panel", review: "senate-panel", audit: "audit-panel" },
    admin: { home: "admin-panel", setup: "admin-panel", completeness: "admin-panel", evidence: "evidence-panel", audit: "audit-panel" }
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
    progress: ["My exam progress", "See the evidence recorded for your own assessments."],
    reports: ["My reports", "See updates on the missing marks you reported."],
    batches: ["Upload and batches", "Upload marks and follow their progress."],
    verify: ["Review batches", "Check submitted marks and approve them for processing."],
    process: ["Process batches", "Record exam-office processing."],
    import: ["Publish marks", "Make processed marks available to students."],
    setup: ["Institution setup", "Users, courses, rosters, assessments and release policies."],
    completeness: ["Unit completeness", "Find missing and delayed assessment components across your courses."],
    review: ["Senate approvals", "Approve or defer final-result batches with a meeting reference."],
    evidence: ["Assessment evidence", "Track attendance, scripts, custody and marking before marks are submitted."],
    audit: ["Batch history", "Follow the handoffs and see what changed."]
  };
  const item = titles[view] || titles.home;
  $("#page-title").textContent = item[0];
  $("#page-subtitle").textContent = item[1];
}

function buildNav() {
  const role = state.user.role;
  const views = {
    student: [["home", "Dashboard"], ["marks", "My marks"], ["progress", "Exam progress"], ["reports", "My reports"], ["audit", "History"]],
    lecturer: [["home", "Dashboard"], ["completeness", "Unit completeness"], ["batches", "Upload & batches"], ["evidence", "Exam evidence"], ["reports", "Issues"], ["audit", "History"]],
    reviewer: [["home", "Dashboard"], ["verify", "Review batches"], ["evidence", "Exam evidence"], ["audit", "History"]],
    exam_office: [["home", "Dashboard"], ["process", "Process batches"], ["evidence", "Exam evidence"], ["audit", "History"]],
    portal_operator: [["home", "Dashboard"], ["import", "Publish marks"], ["audit", "History"]],
    senate_office: [["home", "Dashboard"], ["review", "Senate approvals"], ["audit", "History"]],
    admin: [["home", "Dashboard"], ["completeness", "Unit completeness"], ["setup", "Setup"], ["evidence", "Exam evidence"], ["audit", "History"]]
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
    senate_office: [["Awaiting decision", counts.pending_senate]],
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
  const [marksData, reportsData, notificationData, progressData, readinessData, attachmentsData] = await Promise.all([
    api("/api/student/marks"),
    api("/api/student/reports"),
    api("/api/student/notifications"),
    api("/api/student/progress"),
    api("/api/student/unit-readiness"),
    api("/api/evidence/attachments?owner_type=CASE")
  ]);
  state.studentAttachments = attachmentsData.attachments || [];
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

  const readinessRoot = $("#student-unit-readiness");
  const readinessMessages = {
    ALL_COMPONENTS_PUBLISHED: "Every assessment currently configured for this unit has an official numeric mark. This is a completeness check only; MarkTrail is not calculating a final unit total or assuming CAT/final-exam weighting.",
    OFFICIAL_NO_MARK_OUTCOME: "Every configured assessment has an official outcome, but at least one component is explicitly recorded as NO_MARK. There is no numeric total to calculate from this set of outcomes.",
    MISSING_COMPONENTS: "At least one assessment component is missing from the submitted or published marks. The unit result is not complete.",
    AWAITING_COMPONENTS: "One or more assessment components are still awaiting submission, review, Senate approval or portal publication.",
    CONFIGURATION_REQUIRED: "At least one assessment still has an unclassified release policy. The department administrator must classify it before the result workflow can continue.",
    NO_ASSESSMENTS_CONFIGURED: "No assessments are configured for this unit in MarkTrail. Contact your department if you expected to see CATs or a final examination."
  };
  readinessRoot.innerHTML = readinessData.courses.length
    ? readinessData.courses.map((course) => {
        const componentRows = course.components.map((component) => {
          const mark = component.status === "RECORDED" && component.published_mark !== null
            ? Number(component.published_mark).toFixed(
                Number(component.published_mark) % 1 ? 2 : 0
              ) + "/" + component.max_mark
            : component.status === "NO_MARK"
              ? "No mark awarded"
              : "—";
          return "<tr><td>" + esc(component.assessment) + "</td><td>" +
            badge(component.status) + "</td><td><strong>" + esc(mark) + "</strong></td></tr>";
        }).join("");
        return '<article class="unit-readiness-card"><div class="issue-top"><div><p class="eyebrow">' +
          esc(course.course) + '</p><h3>' + esc(course.course_title) + '</h3></div>' +
          badge(course.readiness) + '</div><p class="muted">' +
          esc(readinessMessages[course.readiness] || "Review the component statuses below.") +
          '</p><div class="unit-readiness-count">' +
          esc(course.complete_component_count) + " of " + esc(course.component_count) +
          " components have an official outcome</div>" +
          '<div class="table-wrap"><table><thead><tr><th>Assessment component</th><th>Status</th><th>Published mark</th></tr></thead><tbody>' +
          (componentRows || '<tr><td colspan="3">No assessment components have been configured.</td></tr>') +
          '</tbody></table></div><small class="muted">' + esc(course.total_note) + '</small></article>';
      }).join("")
    : '<div class="card"><p class="muted">No unit result components are linked to your account yet.</p></div>';

  const progressRoot = $("#student-progress");
  progressRoot.innerHTML = progressData.progress.length
    ? progressData.progress.map((item) => {
        const attendance = item.attendance_status
          ? badge(item.attendance_status)
          : '<span class="badge muted">Not recorded</span>';
        const signature = item.signature_recorded === null
          ? "Not checked"
          : (item.signature_recorded ? "Recorded" : "Not recorded");
        const script = item.script_status
          ? badge(item.script_status)
          : '<span class="badge muted">No receipt recorded</span>';
        const markEntry = item.mark_entry_status === "NOT_ENTERED"
          ? '<span class="badge muted">Not entered</span>'
          : badge(item.mark_entry_status);
        const result = badge(item.result_status);
        const evidenceCases = (item.cases || []).map((caseItem) => {
          const attachments = state.studentAttachments.filter((file) =>
            file.owner_type === "CASE" && file.owner_id === caseItem.id
          );
          const uploadForm = ["RESOLVED", "DISMISSED"].includes(caseItem.status)
            ? '<small class="muted">This case has a final decision. Contact your department about an appeal or review.</small>'
            : '<form class="student-case-attachment-form" data-case-attachment="' + esc(caseItem.id) + '">' +
              '<label>Attach supporting evidence (PDF, PNG or JPEG; max 10 MB)' +
              '<input type="file" name="evidence_file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required></label>' +
              '<button class="button secondary" type="submit">Upload evidence</button></form>';
          return '<div class="student-case-status"><span>' + esc(evidenceCaseLabel(caseItem.category)) + '</span>' +
            badge(caseItem.status) + '<small>' + esc(caseItem.id) + '</small>' +
            renderEvidenceAttachmentList(attachments) + uploadForm + '</div>';
        }).join("");
        const lecturerCard = !item.session_id
          ? '<span class="muted">No exam session recorded</span>'
          : ["FINAL_EXAM", "SPECIAL_EXAM"].includes(item.session_type)
            ? (item.lecturer_card_signed
              ? badge("success", "Lecturer signed")
              : '<span class="badge warning">Awaiting lecturer signature</span>')
            : '<span class="muted">Not required</span>';
        const session = item.evidence_available
          ? '<p class="muted">' + esc(item.exam_at || "Exam time not recorded") +
            (item.venue ? " · " + esc(item.venue) : "") + '</p>'
          : '<p class="muted">No examination evidence has been captured in MarkTrail for this assessment yet.</p>';
        const studentEvidenceForm = item.evidence_available
          ? '<form class="student-evidence-report" data-evidence-report-session="' + esc(item.session_id) + '">' +
            '<label>What needs checking?' +
            '<select name="category" required>' +
            '<option value="">Choose an issue</option>' +
            '<option value="ATTENDANCE">I attended but attendance is missing or incorrect</option>' +
            '<option value="SIGNATURE">My attendance signature is missing or disputed</option>' +
            '<option value="SCRIPT_SUBMISSION">I submitted my answer booklet but script receipt is missing</option>' +
            '<option value="OTHER">Another examination evidence issue</option>' +
            '</select></label>' +
            '<label>Explain what happened' +
            '<textarea name="description" rows="3" maxlength="1000" minlength="10" required placeholder="Tell the department what you experienced and what evidence you can help them locate."></textarea></label>' +
            '<button type="submit" class="button secondary">Report an evidence issue</button>' +
            '<small class="muted">Your report opens a review case. It does not create or change a mark.</small></form>'
          : '';
        return '<article class="student-progress-card"><div class="issue-top"><div><p class="eyebrow">' +
          esc(item.course) + '</p><h3>' + esc(item.assessment) + '</h3></div>' +
          (item.session_status ? badge(item.session_status) : '<span class="badge muted">No session</span>') +
          '</div>' + session +
          '<div class="student-progress-states">' +
          '<div><span>Attendance</span>' + attendance + '</div>' +
          '<div><span>Signature on register</span><strong>' + esc(signature) + '</strong></div>' +
          '<div><span>Script receipt</span>' + script + '</div>' +
          '<div><span>Lecturer exam-card signature</span>' + lecturerCard + '</div>' +
          '<div><span>Marks entry</span>' + markEntry + '</div>' +
          '<div><span>Result stage</span>' + result + '</div>' +
          '</div>' +
          (evidenceCases
            ? '<div class="student-cases"><strong>Evidence cases</strong>' + evidenceCases + '</div>'
            : '') +
          studentEvidenceForm +
          '</article>';
      }).join("")
    : '<div class="card"><p class="muted">No assessments are linked to your student account yet. Contact your department if this does not look right.</p></div>';

  progressRoot.querySelectorAll(".student-case-attachment-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = form.querySelector('input[type="file"]');
      const button = form.querySelector('button[type="submit"]');
      try {
        button.disabled = true;
        const result = await uploadEvidenceAttachment("CASE", form.dataset.caseAttachment, input.files[0]);
        toast(result.scan_status === "CLEAN"
          ? "Evidence uploaded, malware-scanned and stored privately."
          : "Evidence uploaded into quarantine. Downloads stay blocked until a clean malware scan completes.",
          result.scan_status === "CLEAN" ? "success" : "error");
        await loadStudent();
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

  progressRoot.querySelectorAll(".student-evidence-report").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      const category = String(values.get("category") || "");
      const description = String(values.get("description") || "").trim();
      if (!category || description.length < 10) {
        toast("Choose an issue type and describe what happened in at least 10 characters.", "error");
        return;
      }
      const submit = form.querySelector('button[type="submit"]');
      submit.disabled = true;
      try {
        const result = await api("/api/student/evidence-cases", {
          method: "POST",
          body: JSON.stringify({
            session_id: form.dataset.evidenceReportSession,
            category,
            description
          })
        });
        toast("Evidence report received. Case " + result.case_id + " is now with staff for review.");
        await loadStudent();
      } catch (error) {
        toast(error.message, "error");
        submit.disabled = false;
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


function staffCompletenessCategory(status) {
  if (["MISSING", "MISSING_IN_SUBMISSION"].includes(status)) return "missing";
  if (status === "NOT_SUBMITTED") return "not_submitted";
  if (status === "POLICY_UNCLASSIFIED") return "policy";
  if (["RECORDED", "NO_MARK"].includes(status)) return "complete";
  return "awaiting";
}

function staffCompletenessBadge(status) {
  const labels = {
    RECORDED: ["success", "Published mark"],
    NO_MARK: ["warning", "Official NO_MARK"],
    MISSING: ["danger", "Published as missing"],
    MISSING_IN_SUBMISSION: ["danger", "Missing in submission"],
    NOT_SUBMITTED: ["muted", "Not submitted"],
    POLICY_UNCLASSIFIED: ["warning", "Release policy unclassified"],
    AWAITING_SENATE_APPROVAL: ["warning", "Awaiting Senate"],
    SENATE_DEFERRED: ["warning", "Senate deferred"],
    AWAITING_DEPARTMENT_REVIEW: ["muted", "Department review"],
    AWAITING_EXAM_OFFICE: ["muted", "Exam office"],
    AWAITING_PORTAL_PUBLICATION: ["muted", "Portal publication"],
    AWAITING_PUBLICATION: ["muted", "Awaiting publication"],
    ALL_COMPONENTS_PUBLISHED: ["success", "All components published"],
    OFFICIAL_NO_MARK_OUTCOME: ["warning", "Official NO_MARK outcome"],
    MISSING_COMPONENTS: ["danger", "Missing components"],
    AWAITING_COMPONENTS: ["warning", "Awaiting components"],
    CONFIGURATION_REQUIRED: ["warning", "Policy setup required"],
    NO_ASSESSMENTS_CONFIGURED: ["muted", "No assessments configured"],
    NO_STUDENT_COMPONENTS: ["muted", "No candidate components"]
  };
  const [kind, label] = labels[status] || ["muted", status || "Unknown"];
  return '<span class="badge ' + kind + '">' + esc(label) + "</span>";
}

function renderStaffCompleteness(data, targetSelector) {
  const target = $(targetSelector);
  if (!target) return;
  const courses = data?.courses || [];
  const generatedAt = data?.generated_at
    ? new Date(data.generated_at).toLocaleString()
    : "time unavailable";

  target.innerHTML =
    '<div class="staff-completeness-toolbar">' +
      '<label class="staff-completeness-filter">Find a course, assessment or student' +
        '<input type="search" data-staff-search placeholder="Search course, assessment, name or registration number" autocomplete="off">' +
      '</label>' +
      '<label class="staff-completeness-filter">Candidate status' +
        '<select data-staff-status>' +
          '<option value="all">All statuses</option>' +
          '<option value="missing">Missing</option>' +
          '<option value="not_submitted">Not submitted</option>' +
          '<option value="policy">Release policy needs setup</option>' +
          '<option value="awaiting">Awaiting handoff</option>' +
          '<option value="complete">Published outcomes</option>' +
        '</select>' +
      '</label>' +
      '<div class="staff-completeness-refresh" data-staff-results role="status" aria-live="polite"></div>' +
    '</div>' +
    '<p class="muted staff-completeness-note">' +
      esc(data?.unit_total_note || "This view reports component status only; it does not calculate a unit total.") +
      " Scope: " +
      esc(data?.scope === "ALL_COURSES" ? "All institution courses" : "Your assigned courses") +
      " · Last refreshed " + esc(generatedAt) +
    "</p>" +
    '<div class="staff-completeness-list" data-staff-course-results></div>';

  const searchInput = target.querySelector("[data-staff-search]");
  const statusSelect = target.querySelector("[data-staff-status]");
  const resultsNode = target.querySelector("[data-staff-results]");
  const listNode = target.querySelector("[data-staff-course-results]");

  function paint() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    const selectedStatus = statusSelect.value;
    let visibleCourses = 0;
    let visibleAssessments = 0;
    let visibleCandidates = 0;

    const cards = courses.map((course) => {
      const courseText = [course.course, course.course_title].join(" ").toLocaleLowerCase();
      const courseMatches = Boolean(query) && courseText.includes(query);
      const assessments = (course.assessments || []).map((assessment) => {
        const assessmentText = [
          assessment.assessment,
          assessment.release_policy,
          assessment.pipeline_stage
        ].join(" ").toLocaleLowerCase();
        const assessmentMatches = Boolean(query) && assessmentText.includes(query);
        const searchMatchesScope = !query || courseMatches || assessmentMatches;
        const sourceStudents = assessment.students || [];
        const students = sourceStudents
          .filter((student) => {
            const categoryMatches =
              selectedStatus === "all" ||
              staffCompletenessCategory(student.status) === selectedStatus;
            const studentText = [
              student.full_name,
              student.registration_number
            ].join(" ").toLocaleLowerCase();
            return categoryMatches &&
              (searchMatchesScope || studentText.includes(query));
          })
          .sort((a, b) => {
            const priority = (status) => (
              ["MISSING", "MISSING_IN_SUBMISSION"].includes(status) ? 0 :
              status === "POLICY_UNCLASSIFIED" ? 1 :
              status === "NOT_SUBMITTED" ? 2 :
              ["RECORDED", "NO_MARK"].includes(status) ? 4 : 3
            );
            return priority(a.status) - priority(b.status) ||
              String(a.registration_number || a.full_name).localeCompare(
                String(b.registration_number || b.full_name)
              );
          });

        const emptyAssessmentMatches =
          sourceStudents.length === 0 &&
          selectedStatus === "all" &&
          (!query || searchMatchesScope);
        if (!students.length && !emptyAssessmentMatches) return "";

        visibleAssessments += 1;
        visibleCandidates += students.length;
        const counts = assessment.counts || {};
        const table = students.length
          ? '<div class="table-wrap"><table><thead><tr><th>Student</th><th>Registration number</th><th>Component status</th></tr></thead><tbody>' +
            students.map((student) =>
              '<tr><td>' + esc(student.full_name) + '</td><td>' +
              esc(student.registration_number || "—") + '</td><td>' +
              staffCompletenessBadge(student.status) + "</td></tr>"
            ).join("") + "</tbody></table></div>"
          : '<p class="muted">No students are enrolled or present on this assessment’s locked examination roster.</p>';

        const shouldOpen = Boolean(query) || selectedStatus !== "all";
        return (
          '<details class="staff-assessment-detail"' + (shouldOpen ? " open" : "") + '><summary><span><strong>' +
          esc(assessment.assessment) + '</strong><small>' +
          esc(assessment.release_policy || "UNCLASSIFIED") + " · " +
          esc(assessment.pipeline_stage || "NOT SUBMITTED") +
          '</small></span><span class="staff-assessment-counts">' +
          esc(students.length) + "/" + esc(counts.total || 0) + " shown · " +
          esc(counts.missing || 0) + " missing · " +
          esc(counts.no_mark || 0) + " official NO_MARK</span></summary>" +
          table +
          "</details>"
        );
      }).join("");

      const hasNoAssessments = !(course.assessments || []).length &&
        selectedStatus === "all" &&
        (!query || courseMatches);
      if (!assessments.trim() && !hasNoAssessments) return "";

      visibleCourses += 1;
      const counts = course.counts || {};
      const metrics = [
        ["complete", "Official outcomes"],
        ["numeric", "Numeric marks"],
        ["no_mark", "Official NO_MARK"],
        ["missing", "Missing"],
        ["not_submitted", "Not submitted"],
        ["awaiting", "Awaiting handoff"],
        ["policy_unclassified", "Policy unclassified"]
      ].map(([key, label]) =>
        '<div><strong>' + esc(counts[key] || 0) + '</strong><span>' + label + "</span></div>"
      ).join("");

      return (
        '<article class="staff-completeness-course"><div class="staff-completeness-course-head"><div><p class="eyebrow">' +
        esc(course.course) + '</p><h3>' + esc(course.course_title) +
        '</h3><p class="muted">' + esc(course.student_count) + " students · " +
        esc(course.assessment_count) + " configured components</p></div>" +
        staffCompletenessBadge(course.readiness) +
        '</div><div class="staff-completeness-metrics">' + metrics + "</div>" +
        (assessments || '<p class="muted">No assessments are configured for this course yet.</p>') +
        "</article>"
      );
    }).join("");

    listNode.innerHTML = cards ||
      '<div class="card staff-completeness-empty"><p>No records match the current search and status filter.</p><p class="muted">Try a different registration number, course or status.</p></div>';
    resultsNode.textContent =
      "Showing " + visibleCourses + " of " + courses.length + " courses · " +
      visibleAssessments + " assessment components · " +
      visibleCandidates + " candidate statuses";
  }

  searchInput.addEventListener("input", paint);
  statusSelect.addEventListener("change", paint);
  paint();
}

// ── Lecturer ─────────────────────────────────────────────────
async function loadLecturer() {
  const [assessmentsData, batchesData, reportsData, completenessData] = await Promise.all([
    api("/api/lecturer/assessments"),
    api("/api/lecturer/batches"),
    api("/api/lecturer/reports"),
    api("/api/staff/unit-completeness")
  ]);
  state.staffCompleteness = completenessData.completeness;
  renderStaffCompleteness(state.staffCompleteness, "#lecturer-completeness");

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
        const result = await api("/api/exam-office/batches/" + encodeURIComponent(button.dataset.processBatch) + "/process", { method: "POST" });
        toast(result.senate_status === "PENDING"
          ? "Exam-office processing recorded. The batch is now awaiting Senate approval."
          : "Processing recorded. The batch is ready for direct portal import.");
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

// ── University Senate ────────────────────────────────────────
async function loadSenate() {
  const data = await api("/api/senate/batches");
  state.senateBatches = data.batches || [];
  const root = $("#senate-batches");
  root.innerHTML = state.senateBatches.length
    ? state.senateBatches.map((batch) =>
        '<article class="issue senate-batch" data-senate-batch="' + esc(batch.id) + '">' +
        '<div class="issue-top"><div><div class="issue-title">' +
        esc(batch.course + " · " + batch.assessment) + '</div><p class="muted">' +
        esc(batch.lecturer_name + " · " + batch.student_count + " students · revision " + batch.revision) +
        '</p></div>' + badge(batch.senate_status) + '</div>' +
        '<p class="muted">This assessment is configured for Senate approval. Marks remain unpublished until an approval decision is recorded.</p>' +
        '<div class="form-grid senate-decision-fields">' +
        '<label>Meeting / minutes reference<input data-senate-meeting maxlength="120" placeholder="e.g. Senate 04/2026 · Min 12"></label>' +
        '<label>Decision reason<textarea data-senate-reason rows="2" maxlength="1000" placeholder="Required when deferring"></textarea></label>' +
        '</div><div class="actions">' +
        '<button type="button" class="button primary" data-senate-approve="' + esc(batch.id) + '">Approve for release</button>' +
        '<button type="button" class="button secondary" data-senate-defer="' + esc(batch.id) + '">Defer result</button>' +
        '<button type="button" class="button ghost" data-audit-batch="' + esc(batch.id) + '">View history</button>' +
        '</div></article>'
      ).join("")
    : '<div class="card"><p class="muted">No final-result batches are awaiting a Senate decision.</p></div>';

  root.querySelectorAll("[data-senate-approve], [data-senate-defer]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-senate-batch]");
      const meeting = card.querySelector("[data-senate-meeting]").value.trim();
      const reason = card.querySelector("[data-senate-reason]").value.trim();
      const decision = button.hasAttribute("data-senate-approve") ? "APPROVED" : "DEFERRED";
      if (meeting.length < 4) {
        toast("Enter the Senate meeting or minutes reference.", "error");
        return;
      }
      if (decision === "DEFERRED" && reason.length < 8) {
        toast("Add a reason before deferring this result.", "error");
        return;
      }
      if (!confirm(
        decision === "APPROVED"
          ? "Record Senate approval for this exact batch revision? The result will become eligible for portal import."
          : "Defer this result? It will remain blocked from publication until a later Senate decision."
      )) return;

      button.disabled = true;
      try {
        await api("/api/senate/batches/" + encodeURIComponent(button.dataset.senateApprove || button.dataset.senateDefer) + "/decision", {
          method: "POST",
          body: JSON.stringify({ decision, meeting_reference: meeting, reason })
        });
        toast(decision === "APPROVED"
          ? "Senate approval recorded. The result is now eligible for portal import."
          : "Senate deferral recorded. The result remains unpublished.");
        await loadSenate();
        const dashboard = await api("/api/dashboard");
        renderStats(dashboard);
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

  root.querySelectorAll("[data-audit-batch]").forEach((button) => {
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
  const [users, coursesData, batches, assessmentsData, completenessData] = await Promise.all([
    api("/api/admin/users"),
    api("/api/admin/courses"),
    api("/api/admin/batches"),
    api("/api/admin/assessments"),
    api("/api/staff/unit-completeness")
  ]);
  state.staffCompleteness = completenessData.completeness;
  renderStaffCompleteness(state.staffCompleteness, "#admin-completeness");
  state.adminUsers = users.users;
  state.adminCourses = coursesData.courses;
  state.adminBatches = batches.batches;
  state.adminAssessments = assessmentsData.assessments || [];

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

  const assessmentPolicies = $("#admin-assessments");
  assessmentPolicies.innerHTML = state.adminAssessments.length
    ? '<table><thead><tr><th>Course · Assessment</th><th>Policy</th><th>Batch state</th><th>Classify / update</th></tr></thead><tbody>' +
      state.adminAssessments.map((item) => {
        const locked = item.pipeline_stage === "PUBLISHED" ||
          ["PENDING", "DEFERRED", "APPROVED"].includes(item.senate_status);
        const options =
          '<option value="" disabled' + (item.release_policy === "UNCLASSIFIED" ? " selected" : "") + '>Choose release policy</option>' +
          ["DIRECT", "SENATE"].map((policy) =>
            '<option value="' + policy + '"' + (item.release_policy === policy ? " selected" : "") + ">" +
            (policy === "DIRECT" ? "Direct release" : "Senate approval") + "</option>"
          ).join("");
        return '<tr><td><strong>' + esc(item.course_code + " · " + item.name) +
          '</strong><small class="muted">' + esc(item.course_title) + '</small></td>' +
          "<td>" + badge(item.release_policy) + "</td>" +
          "<td>" + (item.batch_id ? badge(item.pipeline_stage || "UNKNOWN") : '<span class="muted">No batch yet</span>') +
          (item.senate_status ? '<small class="muted">Senate: ' + esc(item.senate_status) + "</small>" : "") + "</td>" +
          '<td><form class="release-policy-form" data-assessment-id="' + esc(item.id) + '">' +
          '<select name="release_policy" aria-label="Release policy for ' + esc(item.name) + '"' +
          (locked ? " disabled" : "") + ">" + options + "</select>" +
          '<input name="reason" maxlength="1000" placeholder="Reason for classification / change"' +
          (locked ? " disabled" : "") + ">" +
          '<button class="button secondary"' + (locked ? " disabled" : "") + ">Save policy</button>" +
          (locked ? '<small class="muted">Locked after Senate decision or publication.</small>' : "") +
          "</form></td></tr>";
      }).join("") + "</tbody></table>"
    : '<p class="muted">No assessments available.</p>';

  assessmentPolicies.querySelectorAll(".release-policy-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      const policy = String(values.get("release_policy") || "");
      const reason = String(values.get("reason") || "").trim();
      if (!["DIRECT", "SENATE"].includes(policy)) {
        toast("Choose DIRECT or SENATE.", "error");
        return;
      }
      if (reason.length < 8) {
        toast("Explain the policy classification in at least 8 characters.", "error");
        return;
      }
      const button = form.querySelector("button");
      button.disabled = true;
      try {
        await api("/api/admin/assessments/" + encodeURIComponent(form.dataset.assessmentId) + "/release-policy", {
          method: "POST",
          body: JSON.stringify({ release_policy: policy, reason })
        });
        toast("Assessment release policy updated.");
        await loadAdmin();
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

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
            SENATE_APPROVAL_REQUESTED: "Sent to Senate for approval",
            SENATE_APPROVED: "Senate approved result",
            SENATE_DEFERRED: "Senate deferred result",
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
    const senateDecisions = (data.senate_decisions || []).map((decision) =>
      '<div class="timeline-item"><strong>' +
      esc(decision.decision + " · Decision " + decision.decision_number + " · Batch revision " + decision.revision) +
      '</strong><span>' +
      esc(decision.meeting_reference) +
      (decision.actor_name ? " · recorded by " + esc(decision.actor_name) : "") +
      '</span><small>' + esc(formatDateTime(decision.created_at)) +
      (decision.reason ? " · " + esc(decision.reason) : "") +
      '</small></div>'
    ).join("");

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
      '</p></div>' +
      (senateDecisions
        ? '<div class="card"><p class="eyebrow">SENATE DECISIONS</p><div class="timeline">' + senateDecisions + '</div></div>'
        : "") +
      '<div class="card"><p class="eyebrow">HANDOFFS</p><div class="timeline">' +
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



// ── Assessment evidence workspace ───────────────────────────
function evidenceIssueLabel(code) {
  const labels = {
    ATTENDANCE_NOT_RECORDED: "Attendance decision not recorded",
    ATTENDANCE_DISPUTED: "Attendance is disputed",
    ATTENDANCE_SIGNATURE_STATUS_CONFLICT: "Signed register conflicts with absent status",
    ATTENDANCE_SIGNATURE_MISSING: "Present, but signature is missing",
    LECTURER_EXAM_CARD_SIGNOFF_PENDING: "Lecturer has not signed the physical exam card",
    EXAM_CARD_SIGNOFF_EVIDENCE_CONFLICT: "Exam-card sign-off conflicts with examination evidence",
    EXAM_CARD_CHECK_NOT_RECORDED: "Exam-card check not recorded",
    STUDENT_ID_CHECK_NOT_RECORDED: "Student-ID check not recorded",
    SCRIPT_NOT_RECEIVED: "Candidate recorded present; no script receipt",
    SCRIPT_RECEIVED_FOR_RECORDED_ABSENT: "Script received for a candidate recorded absent",
    SCRIPT_WITHOUT_ATTENDANCE: "Script has no attendance record",
    SCRIPT_HANDOFF_NOT_ACCEPTED: "Script handover awaits acceptance",
    SCRIPT_NOT_MARKED: "Script received but not marked",
    MARK_ENTRY_NOT_FOUND: "Script marked; no marks entry found",
    MARK_RECORDED_FOR_RECORDED_ABSENT: "Mark recorded for a candidate recorded absent",
    MARK_WITHOUT_SCRIPT_RECEIPT: "Mark exists but no script receipt was recorded",
    SCRIPT_UNIDENTIFIED: "Script received but candidate is unidentified"
  };
  return labels[code] || code.replaceAll("_", " ").toLowerCase();
}

function evidenceStaffOptions(selectedId) {
  return state.evidenceStaff.map((person) =>
    '<option value="' + esc(person.id) + '"' +
    (Number(selectedId) === Number(person.id) ? " selected" : "") + ">" +
    esc(person.full_name + " · " + person.role.replaceAll("_", " ")) + "</option>"
  ).join("");
}

async function loadEvidence() {
  const [assessmentData, staffData, caseData, attachmentData] = await Promise.all([
    api("/api/evidence/assessments"),
    api("/api/evidence/staff"),
    api("/api/evidence/cases"),
    api("/api/evidence/attachments?owner_type=CASE")
  ]);
  state.evidenceAssessments = assessmentData.assessments || [];
  state.evidenceStaff = staffData.staff || [];
  state.evidenceCases = caseData.cases || [];
  state.evidenceAttachments = attachmentData.attachments || [];
  renderEvidenceCaseQueue();

  const select = $("#evidence-assessment");
  const previous = state.evidenceSelectedAssessment || select.value;
  select.innerHTML = state.evidenceAssessments.length
    ? state.evidenceAssessments.map((assessment) =>
        '<option value="' + esc(assessment.id) + '">' +
        esc(assessment.course_code + " · " + assessment.name) +
        " · " + esc(assessment.enrolled_count) + " students</option>"
      ).join("")
    : '<option value="">No assessments available for your account</option>';
  state.evidenceSelectedAssessment = state.evidenceAssessments.some((item) => item.id === previous)
    ? previous
    : (state.evidenceAssessments[0]?.id || "");
  select.value = state.evidenceSelectedAssessment;
  if (!state.evidenceSelectedAssessment) {
    $("#evidence-sessions").innerHTML = '<p class="muted">No assessments are assigned to this account.</p>';
    $("#evidence-workspace").innerHTML = "";
    return;
  }
  await loadEvidenceAssessment(state.evidenceSelectedAssessment);
}

function evidenceCaseLabel(code) {
  return String(code || "UNKNOWN").replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderEvidenceCaseQueue() {
  const root = $("#evidence-case-queue");
  if (!root) return;
  const cases = state.evidenceCases || [];
  root.innerHTML = cases.length
    ? cases.map((item) => {
        const identity = item.registration_number
          ? esc(item.registration_number) + " · " + esc(item.full_name || "Candidate")
          : (item.script_ref ? "Script " + esc(item.script_ref) : "Candidate record");
        const assignment = item.assigned_user_name
          ? "Owned by " + esc(item.assigned_user_name) + " · " + esc((item.assigned_role || "").replaceAll("_", " "))
          : item.assigned_role
            ? "Queue: " + esc(item.assigned_role.replaceAll("_", " "))
            : "Unassigned";
        const caseHistory = (item.events || []).map((event) =>
          '<div class="case-history-item"><strong>' +
          esc(evidenceCaseLabel(event.event_type)) + '</strong><span>' +
          esc(event.actor_name || "System") + " · " + esc(event.created_at) +
          '</span>' + (event.note ? '<small>' + esc(event.note) + '</small>' : '') +
          '</div>'
        ).join("");
        const attachments = state.evidenceAttachments.filter((file) =>
          file.owner_type === "CASE" && file.owner_id === item.id
        );
        const uploadForm = ["RESOLVED", "DISMISSED"].includes(item.status)
          ? ""
          : '<form class="staff-case-attachment-form" data-case-attachment="' + esc(item.id) + '">' +
            '<label>Add supporting evidence (PDF, PNG or JPEG; max 10 MB)' +
            '<input type="file" name="evidence_file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required></label>' +
            '<button class="button secondary" type="submit">Attach evidence</button></form>';
        const canDecide = ["reviewer", "admin"].includes(state.user.role) &&
          ["OPEN", "EVIDENCE_CLEARED"].includes(item.status);
        const decision = canDecide
          ? '<label>Decision note<textarea data-case-reason="' + esc(item.id) + '" rows="2" maxlength="1000" placeholder="Record what was checked and why this case can close"></textarea></label>' +
            '<div class="actions"><button type="button" class="button primary" data-case-decision="RESOLVED" data-case-id="' + esc(item.id) + '">Resolve case</button>' +
            '<button type="button" class="button secondary" data-case-decision="DISMISSED" data-case-id="' + esc(item.id) + '">Dismiss as not applicable</button></div>'
          : "";
        return '<article class="issue evidence-case" data-case-card="' + esc(item.id) + '">' +
          '<div class="issue-top"><div><strong>' + esc(item.course + " · " + item.assessment) + '</strong>' +
          '<p class="muted">' + identity + '</p></div><div class="case-badges">' +
          badge(item.severity) + badge(item.status) + '</div></div>' +
          '<p class="case-category">' + esc(evidenceCaseLabel(item.category)) + '</p>' +
          '<small class="muted">' + assignment + ' · Updated ' + esc(item.updated_at) + '</small>' +
          (item.status === "EVIDENCE_CLEARED"
            ? '<p class="muted">The source evidence no longer shows this exception. A reviewer must confirm the case outcome.</p>'
            : "") +
          (caseHistory ? '<div class="case-history"><strong>Case history</strong>' + caseHistory + '</div>' : '') +
          '<div class="case-attachments"><strong>Supporting documents</strong>' +
          renderEvidenceAttachmentList(attachments) + uploadForm + '</div>' +
          decision + '</article>';
      }).join("")
    : '<div class="card"><p class="muted">No evidence cases are currently assigned to this role or account.</p></div>';

  root.querySelectorAll(".staff-case-attachment-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = form.querySelector('input[type="file"]');
      const button = form.querySelector('button[type="submit"]');
      try {
        button.disabled = true;
        const result = await uploadEvidenceAttachment("CASE", form.dataset.caseAttachment, input.files[0]);
        toast(result.scan_status === "CLEAN"
          ? "Supporting evidence attached and scanned clean."
          : "Evidence is in quarantine; downloads remain blocked until a clean scan completes.",
          result.scan_status === "CLEAN" ? "success" : "error");
        await loadEvidenceCases();
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

  root.querySelectorAll("[data-case-decision]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-case-card]");
      const reason = card.querySelector("[data-case-reason]").value.trim();
      if (reason.length < 8) {
        toast("Add an investigation outcome of at least 8 characters.", "error");
        return;
      }
      if (!confirm(
        button.dataset.caseDecision === "RESOLVED"
          ? "Confirm that the evidence case has been investigated and resolved?"
          : "Confirm that this exception is not applicable and should be dismissed?"
      )) return;
      button.disabled = true;
      try {
        await api("/api/evidence/cases/" + encodeURIComponent(button.dataset.caseId) + "/decision", {
          method: "POST",
          body: JSON.stringify({
            decision: button.dataset.caseDecision,
            reason
          })
        });
        toast("Evidence case " + button.dataset.caseDecision.toLowerCase() + ".");
        await loadEvidenceCases();
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });
}

async function loadEvidenceCases() {
  const [data, attachments] = await Promise.all([
    api("/api/evidence/cases"),
    api("/api/evidence/attachments?owner_type=CASE")
  ]);
  state.evidenceCases = data.cases || [];
  state.evidenceAttachments = attachments.attachments || [];
  renderEvidenceCaseQueue();
}

async function loadEvidenceAssessment(assessmentId) {
  state.evidenceSelectedAssessment = assessmentId;
  const data = await api("/api/evidence/assessments/" + encodeURIComponent(assessmentId));
  state.evidenceSessions = data.sessions || [];
  if (!state.evidenceSessions.some((item) => item.id === state.evidenceSelectedSession)) {
    state.evidenceSelectedSession = state.evidenceSessions[0]?.id || "";
  }
  renderEvidenceSessions();
  if (state.evidenceSelectedSession) {
    await loadEvidenceSession(state.evidenceSelectedSession);
  } else {
    state.evidenceDetail = null;
    $("#evidence-workspace").innerHTML =
      '<div class="card"><p class="muted">No examination session exists yet. Create one above to snapshot the candidate register.</p></div>';
  }
}

async function loadEvidenceSession(sessionId) {
  state.evidenceSelectedSession = sessionId;
  const [detail, attachments] = await Promise.all([
    api("/api/evidence/sessions/" + encodeURIComponent(sessionId)),
    api("/api/evidence/attachments?owner_type=SESSION&owner_id=" + encodeURIComponent(sessionId))
  ]);
  const scriptRecords = [
    ...(detail.candidates || []).filter((candidate) => candidate.script).map((candidate) => candidate.script),
    ...(detail.unidentified_scripts || [])
  ];
  const scriptFiles = await Promise.all(scriptRecords.map((script) =>
    api("/api/evidence/attachments?owner_type=SCRIPT&owner_id=" + encodeURIComponent(script.id))
  ));
  detail.scriptAttachments = Object.fromEntries(
    scriptRecords.map((script, index) => [script.id, scriptFiles[index].attachments || []])
  );
  state.evidenceDetail = detail;
  state.evidenceDetail.attachments = attachments.attachments || [];
  renderEvidenceSessions();
  renderEvidenceSession();
}

function renderEvidenceSessions() {
  const root = $("#evidence-sessions");
  if (!state.evidenceSessions.length) {
    root.innerHTML = '<p class="muted">No examination sessions yet for this assessment.</p>';
    return;
  }
  root.innerHTML = state.evidenceSessions.map((session) =>
    '<button type="button" class="evidence-session' +
    (session.id === state.evidenceSelectedSession ? " active" : "") +
    '" data-evidence-open-session="' + esc(session.id) + '">' +
    '<span><strong>' + esc(session.venue) + '</strong><small>' +
    esc((session.session_type || "UNCLASSIFIED").replaceAll("_", " ")) + " · " +
    esc(session.exam_at) + " · " + esc(session.candidate_count) + " candidates</small></span>" +
    badge(session.status) + "</button>"
  ).join("");
  root.querySelectorAll("[data-evidence-open-session]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await loadEvidenceSession(button.dataset.evidenceOpenSession);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });
}

function renderEvidenceSession() {
  const root = $("#evidence-workspace");
  const data = state.evidenceDetail;
  if (!data) {
    root.innerHTML = "";
    return;
  }
  const session = data.session;
  const summary = data.summary;
  const registerClosed = session.status === "CLOSED";
  const canCorrectClosedRegister = registerClosed && ["reviewer", "admin"].includes(state.user.role);
  const locked = registerClosed && !canCorrectClosedRegister;
  const requiresExamCardSignoff = ["FINAL_EXAM", "SPECIAL_EXAM"].includes(session.session_type);
  const candidates = data.candidates || [];
  const candidateOptions = candidates.map((candidate) =>
    '<option value="' + esc(candidate.student_id) + '">' +
    esc((candidate.registration_number || "No reg number") + " · " + candidate.full_name) +
    "</option>"
  ).join("");

  let rosterRows = candidates.map((candidate) => {
    const attendance = candidate.attendance || {};
    const recordedStatus = attendance.attendance_status || "";
    const script = candidate.script;
    const cardSignoff = candidate.card_signoff;
    const cardSignoffCell = !requiresExamCardSignoff
      ? '<span class="muted">Not required</span>'
      : cardSignoff
        ? badge("success", "Signed") + '<small>' + esc(cardSignoff.signed_by_name || "Lecturer") + " · " + esc(cardSignoff.signed_at) + "</small>"
        : state.user.role === "lecturer" && registerClosed
          ? '<button type="button" class="button secondary" data-sign-exam-card="' + esc(candidate.student_id) + '">Confirm physical card signed</button>'
          : state.user.role === "lecturer"
            ? '<span class="muted">Available after the register closes</span>'
            : '<span class="badge warning">Awaiting lecturer</span>';
    const markLabel = candidate.mark && candidate.mark.candidate_status === "RECORDED"
      ? "Mark entered"
      : "No mark entry";
    return "<tr data-evidence-candidate=\"" + esc(candidate.student_id) + "\">" +
      "<td><strong>" + esc(candidate.registration_number || "—") + "</strong><small>" + esc(candidate.full_name) + "</small></td>" +
      '<td><select data-attendance-status ' + (locked ? "disabled" : "") + ">" +
      '<option value="">Not recorded</option>' +
      ["PRESENT", "ABSENT", "EXCUSED", "CONTESTED"].map((option) =>
        '<option value="' + option + '"' + (recordedStatus === option ? " selected" : "") + ">" +
        option.replaceAll("_", " ") + "</option>"
      ).join("") + "</select></td>" +
      '<td><label class="check-inline"><input type="checkbox" data-signature ' +
      (attendance.signature_present ? "checked" : "") + (locked ? " disabled" : "") +
      "> Signed</label></td>" +
      '<td><label class="check-inline"><input type="checkbox" data-exam-card ' +
      (attendance.exam_card_seen ? "checked" : "") + (locked ? " disabled" : "") +
      "> Card</label></td>" +
      '<td><label class="check-inline"><input type="checkbox" data-student-id ' +
      (attendance.student_id_seen ? "checked" : "") + (locked ? " disabled" : "") +
      "> ID</label></td>" +
      "<td>" + cardSignoffCell + "</td>" +
      "<td>" + (script ? badge(script.status) + '<small>' + esc(script.script_ref) + "</small>" : '<span class="muted">No receipt</span>') + "</td>" +
      "<td>" + esc(markLabel) + "</td>" +
      '<td><input type="text" data-attendance-note maxlength="1000" placeholder="' +
      (registerClosed ? "Reason required for correction" : "Optional incident note") + '" value="' +
      esc(attendance.note || "") + '"' + (locked ? " disabled" : "") + ">" +
      '<button type="button" class="button secondary" data-save-attendance="' + esc(candidate.student_id) + '"' +
      (locked ? " disabled" : "") + ">Save</button></td></tr>";
  }).join("");

  const activity = (data.activity || []).slice().reverse().map((event) => {
    let title = event.event_type.replaceAll("_", " ").toLowerCase();
    let subject = "";
    let note = "";

    if (event.category === "SESSION") {
      title = event.event_type === "SESSION_CREATED"
        ? "Examination session created"
        : "Attendance register closed";
      if (event.metadata) {
        subject = [
          (event.metadata.session_type || "").replaceAll("_", " "),
          event.metadata.venue,
          event.metadata.candidate_count ? event.metadata.candidate_count + " candidates" : ""
        ].filter(Boolean).join(" · ");
      }
    } else if (event.category === "ATTENDANCE") {
      const next = event.new_state?.attendance_status || "updated";
      const previous = event.old_state?.attendance_status;
      title = event.event_type === "CORRECTED" ? "Attendance corrected" : "Attendance recorded";
      subject = (event.registration_number || "Candidate") + " · " + event.candidate_name +
        " · " + (previous ? previous + " → " : "") + next;
      note = event.reason || "";
    } else if (event.category === "EXAM_CARD") {
      title = "Lecturer signed the physical exam card";
      subject = (event.registration_number || "Candidate") + " · " + event.candidate_name;
      note = event.note || "";
    } else if (event.category === "SCRIPT") {
      const labels = {
        RECEIVED: "Script received",
        HANDOFF_REQUESTED: "Script handover requested",
        HANDOFF_ACCEPTED: "Script custody accepted",
        MARKED: "Marking completion recorded",
        FLAGGED: "Script flagged for review",
        IDENTITY_LINKED: "Script identity linked after review"
      };
      title = labels[event.event_type] || title;
      subject = [event.script_ref, event.registration_number, event.candidate_name].filter(Boolean).join(" · ");
      if (event.event_type === "HANDOFF_REQUESTED" && event.recipient_name) {
        subject += " · handed to " + event.recipient_name + " (awaiting acceptance)";
      }
      if (event.event_type === "HANDOFF_ACCEPTED" && event.recipient_name) {
        subject += " · custody transferred from " + event.recipient_name;
      }
      note = event.note || "";
    }

    return '<article class="activity-item">' +
      '<div class="activity-copy"><strong>' + esc(title) + '</strong>' +
      (subject ? '<span>' + esc(subject) + '</span>' : '') +
      (note ? '<p>' + esc(note) + '</p>' : '') +
      '<small>' + esc(event.actor_name || "Unknown staff") + ' · ' +
      esc((event.actor_role || "staff").replaceAll("_", " ")) + ' · ' +
      esc(event.created_at) + '</small></div></article>';
  }).join("");

  const issues = (data.exceptions || []).length
    ? '<div class="evidence-issues">' + data.exceptions.map((issue) =>
        '<div class="evidence-issue"><span>' + esc(issue.registration_number || issue.script_ref || "Unmatched record") +
        " · " + esc(issue.full_name || "") + "</span>" +
        "<strong>" + esc(evidenceIssueLabel(issue.code)) + "</strong>" +
        badge(issue.severity) + "</div>"
      ).join("") + "</div>"
    : '<p class="muted">No reconciliation exceptions detected in the evidence currently recorded.</p>';

  const scripts = candidates.filter((candidate) => candidate.script).map((candidate) => ({
    candidate,
    script: candidate.script
  }));
  const scriptCards = scripts.length
    ? scripts.map(({candidate, script}) => {
        const currentCustodian = Number(script.current_custodian);
        const pendingCustodian = Number(script.pending_custodian);
        let actions = "";
        if (script.status === "HANDOFF_PENDING" && pendingCustodian === Number(state.user.id)) {
          actions = '<p class="muted">This script is awaiting your acceptance.</p><button type="button" class="button primary" data-accept-script="' + esc(script.id) + '">Accept custody</button>';
        } else if (script.status === "HANDOFF_PENDING" && currentCustodian === Number(state.user.id)) {
          actions = '<p class="muted">Handover requested. Waiting for ' + esc(script.pending_custodian_name || "the assigned recipient") + ' to accept custody.</p>';
        } else if (script.status === "HANDOFF_PENDING") {
          actions = '<p class="muted">Script custody handover is awaiting recipient acceptance.</p>';
        } else if (script.status !== "MARKED" && currentCustodian === Number(state.user.id)) {
          actions =
            '<div class="form-grid compact-grid"><label>Hand over to<select data-handoff-recipient="' + esc(script.id) + '">' +
            '<option value="">Choose staff member</option>' + evidenceStaffOptions("") +
            '</select></label><label>Handover note<input data-handoff-note="' + esc(script.id) + '" maxlength="1000" placeholder="e.g. second marker"></label></div>' +
            '<div class="actions"><button type="button" class="button secondary" data-handoff-script="' + esc(script.id) + '">Request handover</button>' +
            '<button type="button" class="button primary" data-mark-script="' + esc(script.id) + '">Marking complete</button></div>';
        } else {
          actions = '<p class="muted">Current custodian: ' + esc(script.current_custodian_name || "Assigned staff member") + '</p>';
        }
        const scriptAttachments = (data.scriptAttachments || {})[script.id] || [];
        const attachmentForm = '<form class="script-attachment-form" data-script-attachment="' + esc(script.id) + '">' +
          '<label>Attach this script or receipt (PDF, PNG or JPEG; max 10 MB)' +
          '<input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required></label>' +
          '<button type="submit" class="button secondary">Attach to script</button></form>';
        return '<div class="script-card"><div class="issue-top"><div><strong>' + esc(script.script_ref) +
          '</strong><div class="muted">' + esc(candidate.registration_number || "") + " · " + esc(candidate.full_name) +
          "</div></div>" + badge(script.status) + "</div><p class=\"muted\">Received " +
          esc(script.received_at || "") + "</p>" + actions +
          '<div class="case-attachments"><strong>Script documents</strong>' +
          renderEvidenceAttachmentList(scriptAttachments) + attachmentForm + '</div></div>';
      }).join("")
    : '<p class="muted">No candidate-linked scripts have been received in this session yet.</p>';

  const orphanCards = (data.unidentified_scripts || []).map((script) => {
    const linkAction = ["reviewer", "exam_office", "admin"].includes(state.user.role)
      ? '<div class="form-grid compact-grid"><label>Match to candidate<select data-link-candidate="' + esc(script.id) +
        '"><option value="">Select candidate</option>' + candidateOptions + '</select></label>' +
        '<label>Reason / evidence<input data-link-reason="' + esc(script.id) +
        '" maxlength="1000" placeholder="Explain how identity was confirmed"></label></div>' +
        '<button type="button" class="button primary" data-link-script="' + esc(script.id) + '">Link verified candidate</button>'
      : '<p class="muted">A reviewer or exam-office officer must verify and link this script to a candidate.</p>';
    const scriptAttachments = (data.scriptAttachments || {})[script.id] || [];
    const attachmentForm = '<form class="script-attachment-form" data-script-attachment="' + esc(script.id) + '">' +
      '<label>Attach this unidentified script or receipt (PDF, PNG or JPEG; max 10 MB)' +
      '<input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required></label>' +
      '<button type="submit" class="button secondary">Attach to script</button></form>';
    return '<div class="script-card"><div class="issue-top"><div><strong>' + esc(script.script_ref) +
      '</strong><div class="muted">Candidate not identified · ' + esc(script.received_at) +
      '</div></div>' + badge("FLAGGED") + "</div><p>" + esc(script.notes || "") + "</p>" + linkAction +
      '<div class="case-attachments"><strong>Script documents</strong>' +
      renderEvidenceAttachmentList(scriptAttachments) + attachmentForm + '</div></div>';
  }).join("");

  root.innerHTML =
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">SESSION OVERVIEW</p><h2>' +
    esc(session.course + " · " + session.assessment) + "</h2><p class=\"muted\">" +
    esc(session.session_type.replaceAll("_", " ") + " · " + session.exam_at + " · " + session.venue) + "</p></div>" + badge(session.status) + "</div>" +
    '<div class="evidence-metrics">' +
    '<div><strong>' + esc(summary.candidates) + '</strong><span>Candidates</span></div>' +
    '<div><strong>' + esc(summary.attendance_recorded) + '</strong><span>Attendance captured</span></div>' +
    '<div><strong>' + esc(summary.scripts_received) + '</strong><span>Scripts received</span></div>' +
    '<div><strong>' + esc(summary.scripts_marked) + '</strong><span>Scripts marked</span></div>' +
    (requiresExamCardSignoff ? '<div><strong>' + esc(summary.exam_cards_signed) + '</strong><span>Exam cards signed</span></div>' : '') +
    '<div><strong>' + esc(summary.exceptions) + '</strong><span>Exceptions</span></div></div>' +
    (registerClosed
      ? (canCorrectClosedRegister
        ? '<p class="muted">This register is closed. You may make a controlled correction as a reviewer or administrator; every change requires a reason and creates an audit event.</p>'
        : '<p class="muted">Attendance register is closed. Historical records remain visible.</p>')
      : '<p class="muted">Record an explicit decision for each candidate. A PRESENT decision without a signature stays PRESENT and raises a signature exception; it is never converted to ABSENT.</p>') +
    (session.status === "OPEN" ? '<div class="actions"><button type="button" class="button secondary" id="close-evidence-session">Close attendance register</button></div>' : "") +
    "</div>" +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">CANDIDATE REGISTER</p><h2>Attendance and checks</h2></div>' +
    (!registerClosed ? '<button type="button" class="button primary" id="save-all-attendance">Save all decisions</button>' : '') +
    '</div><div class="muted">Review every candidate before saving. The bulk action validates the full register and saves it as one transaction.</div>' +
    '<div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Attendance decision</th><th>Signature</th><th>Exam card check</th><th>Student ID</th><th>Lecturer card sign-off</th><th>Script</th><th>Marks</th><th>Incident note / action</th></tr></thead><tbody>' +
    (rosterRows || '<tr><td colspan="9">No candidates in the locked roster.</td></tr>') +
    "</tbody></table></div></div>" +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">SOURCE DOCUMENTS</p><h2>Scanned registers and examination records</h2></div></div>' +
    renderEvidenceAttachmentList(data.attachments || []) +
    '<form id="session-attachment-form" class="form-grid">' +
    '<label>Choose a source document<input id="session-attachment-file" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required></label>' +
    '<div class="actions"><button type="submit" class="button secondary">Upload source document</button></div></form>' +
    '<p class="muted">PDF, PNG and JPEG only · 10 MB per file · Files are private and cannot be downloaded until malware scanning passes.</p></div>' +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">SCRIPT INTAKE</p><h2>Record a collected script</h2></div></div>' +
    '<form id="evidence-script-form" class="form-grid">' +
    '<label>Candidate<select id="evidence-script-student"><option value="">Unidentified / needs review</option>' + candidateOptions + '</select></label>' +
    '<label>Script or booklet reference<input id="evidence-script-ref" maxlength="80" placeholder="e.g. packet-04-seat-18" required></label>' +
    '<label>Receipt / incident note<input id="evidence-script-note" maxlength="1000" placeholder="Required for unidentified scripts"></label>' +
    '<div class="actions"><button type="submit" class="button primary">Record script receipt</button></div></form>' +
    '<p class="muted">Use an institution-approved reference or packet identifier. Do not type marks or sensitive personal details into this reference.</p></div>' +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">SCRIPT CUSTODY</p><h2>Received scripts and handovers</h2></div></div>' +
    scriptCards + orphanCards + "</div>" +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">ACTIVITY HISTORY</p><h2>Evidence chronology</h2></div></div>' +
    (activity ? '<div class="activity-list">' + activity + '</div>' : '<p class="muted">No evidence activity has been recorded yet.</p>') +
    '<p class="muted">History entries are append-only. Corrections appear as new events rather than overwriting what happened previously.</p></div>' +
    '<div class="card"><div class="section-head compact"><div><p class="eyebrow">RECONCILIATION</p><h2>Exceptions to investigate</h2></div></div>' +
    issues + '</div>';

  root.querySelectorAll(".script-attachment-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const file = form.querySelector('input[type="file"]').files[0];
      try {
        button.disabled = true;
        const result = await uploadEvidenceAttachment(
          "SCRIPT", form.dataset.scriptAttachment, file
        );
        toast(result.scan_status === "CLEAN"
          ? "Script evidence attached and scanned clean."
          : "Script evidence is quarantined until a clean malware scan completes.",
          result.scan_status === "CLEAN" ? "success" : "error");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

  $("#session-attachment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector('button[type="submit"]');
    try {
      button.disabled = true;
      const result = await uploadEvidenceAttachment(
        "SESSION", session.id, $("#session-attachment-file").files[0]
      );
      toast(result.scan_status === "CLEAN"
        ? "Source document uploaded and scanned clean."
        : "Document is quarantined until a clean malware scan completes.",
        result.scan_status === "CLEAN" ? "success" : "error");
      await loadEvidenceSession(session.id);
    } catch (error) {
      toast(error.message, "error");
      button.disabled = false;
    }
  });

  const saveAllButton = $("#save-all-attendance");
  if (saveAllButton) saveAllButton.addEventListener("click", async () => {
    const rows = Array.from(root.querySelectorAll("tr[data-evidence-candidate]"));
    const items = [];
    const problems = [];

    for (const row of rows) {
      const status = row.querySelector("[data-attendance-status]").value;
      const candidate = candidates.find((item) => String(item.student_id) === row.dataset.evidenceCandidate);
      const note = row.querySelector("[data-attendance-note]").value.trim();
      if (!status) {
        problems.push((candidate?.registration_number || "Candidate") + ": choose an attendance decision.");
        continue;
      }
      if (["ABSENT", "EXCUSED", "CONTESTED"].includes(status) && note.length < 8) {
        problems.push((candidate?.registration_number || "Candidate") + ": add a reason for " + status.toLowerCase() + ".");
        continue;
      }
      if (registerClosed && note.length < 8) {
        problems.push((candidate?.registration_number || "Candidate") + ": closed-register corrections need a reason.");
        continue;
      }
      items.push({
        student_id: Number(row.dataset.evidenceCandidate),
        attendance_status: status,
        signature_present: row.querySelector("[data-signature]").checked,
        exam_card_seen: row.querySelector("[data-exam-card]").checked,
        student_id_seen: row.querySelector("[data-student-id]").checked,
        note
      });
    }

    if (problems.length) {
      toast(problems.slice(0, 3).join(" "), "error");
      if (problems.length > 3) toast((problems.length - 3) + " more candidate(s) need attention.", "error");
      return;
    }
    if (!items.length) {
      toast("There are no attendance decisions to save.", "error");
      return;
    }
    if (!confirm("Save attendance evidence for all " + items.length + " candidates in one transaction?")) return;

    saveAllButton.disabled = true;
    saveAllButton.textContent = "Saving register…";
    try {
      const result = await api("/api/evidence/sessions/" + encodeURIComponent(session.id) + "/attendance", {
        method: "POST",
        body: JSON.stringify({ items })
      });
      toast("Saved " + result.saved + " attendance decisions.");
      await loadEvidenceSession(session.id);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      saveAllButton.disabled = false;
      saveAllButton.textContent = "Save all decisions";
    }
  });

  root.querySelectorAll("[data-sign-exam-card]").forEach((button) => {
    button.addEventListener("click", async () => {
      const candidate = candidates.find((item) => String(item.student_id) === button.dataset.signExamCard);
      if (!candidate) return;
      const confirmed = confirm(
        "Confirm that you have physically signed " +
        candidate.full_name +
        "'s exam card for " + session.course + " · " + session.assessment +
        ". Only confirm after signing the physical card."
      );
      if (!confirmed) return;
      button.disabled = true;
      try {
        await api("/api/evidence/sessions/" + encodeURIComponent(session.id) + "/exam-card-signoffs", {
          method: "POST",
          body: JSON.stringify({
            items: [{
              student_id: Number(candidate.student_id),
              note: "Lecturer confirmed the physical exam-card signature for this unit examination."
            }]
          })
        });
        toast("Physical exam-card sign-off recorded.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
      }
    });
  });

  root.querySelectorAll("[data-save-attendance]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest("tr");
      const status = row.querySelector("[data-attendance-status]").value;
      if (!status) {
        toast("Choose an attendance decision before saving.", "error");
        return;
      }
      const attendanceNote = row.querySelector("[data-attendance-note]").value.trim();
      if (["ABSENT", "EXCUSED", "CONTESTED"].includes(status) && attendanceNote.length < 8) {
        toast("Add a short reason for an absent, excused or disputed attendance decision.", "error");
        return;
      }
      if (registerClosed && attendanceNote.length < 8) {
        toast("Closed-register corrections require an 8-character reason.", "error");
        return;
      }
      try {
        await api("/api/evidence/sessions/" + encodeURIComponent(session.id) + "/attendance", {
          method: "POST",
          body: JSON.stringify({ items: [{
            student_id: Number(button.dataset.saveAttendance),
            attendance_status: status,
            signature_present: row.querySelector("[data-signature]").checked,
            exam_card_seen: row.querySelector("[data-exam-card]").checked,
            student_id_seen: row.querySelector("[data-student-id]").checked,
            note: attendanceNote
          }] })
        });
        toast("Attendance evidence saved.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  const closeButton = $("#close-evidence-session");
  if (closeButton) closeButton.addEventListener("click", async () => {
    if (!confirm("Close this attendance register? Further attendance changes will require an authorised correction workflow.")) return;
    try {
      await api("/api/evidence/sessions/" + encodeURIComponent(session.id) + "/close", { method: "POST" });
      toast("Attendance register closed.");
      await loadEvidenceAssessment(state.evidenceSelectedAssessment);
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#evidence-script-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const candidateValue = $("#evidence-script-student").value;
    const scriptNote = $("#evidence-script-note").value.trim();
    if ((!candidateValue || registerClosed) && scriptNote.length < 8) {
      toast("Add an explanation for an unidentified or late-received script.", "error");
      return;
    }
    try {
      await api("/api/evidence/sessions/" + encodeURIComponent(session.id) + "/scripts", {
        method: "POST",
        body: JSON.stringify({
          student_id: candidateValue ? Number(candidateValue) : null,
          script_ref: $("#evidence-script-ref").value.trim(),
          note: scriptNote
        })
      });
      $("#evidence-script-ref").value = "";
      $("#evidence-script-note").value = "";
      toast(candidateValue ? "Script receipt recorded." : "Unidentified script quarantined for review.", candidateValue ? "success" : "error");
      await loadEvidenceSession(session.id);
    } catch (error) {
      toast(error.message, "error");
    }
  });

  root.querySelectorAll("[data-mark-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/evidence/scripts/" + encodeURIComponent(button.dataset.markScript) + "/mark", {
          method: "POST",
          body: JSON.stringify({ note: "Marking completion recorded by the current custodian." })
        });
        toast("Script marking completion recorded. Submit the mark through the normal marks-batch workflow.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-handoff-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const scriptId = button.dataset.handoffScript;
      const recipient = root.querySelector('[data-handoff-recipient="' + scriptId + '"]').value;
      const note = root.querySelector('[data-handoff-note="' + scriptId + '"]').value;
      if (!recipient) {
        toast("Choose the staff member who will receive custody.", "error");
        return;
      }
      try {
        await api("/api/evidence/scripts/" + encodeURIComponent(scriptId) + "/handoff", {
          method: "POST",
          body: JSON.stringify({ recipient_id: Number(recipient), note })
        });
        toast("Handover requested. The recipient must accept custody.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-accept-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/evidence/scripts/" + encodeURIComponent(button.dataset.acceptScript) + "/accept", { method: "POST" });
        toast("Script custody accepted.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-link-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const scriptId = button.dataset.linkScript;
      const studentId = root.querySelector('[data-link-candidate="' + scriptId + '"]').value;
      const reason = root.querySelector('[data-link-reason="' + scriptId + '"]').value;
      if (!studentId || reason.trim().length < 8) {
        toast("Choose a candidate and provide the evidence for the match.", "error");
        return;
      }
      try {
        await api("/api/evidence/scripts/" + encodeURIComponent(scriptId) + "/link", {
          method: "POST",
          body: JSON.stringify({ student_id: Number(studentId), reason })
        });
        toast("Script identity linked after review.");
        await loadEvidenceSession(session.id);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });
}

$("#evidence-assessment").addEventListener("change", async (event) => {
  state.evidenceSelectedSession = "";
  try {
    await loadEvidenceAssessment(event.target.value);
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#evidence-session-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const examAt = $("#evidence-exam-at").value;
  const sessionType = $("#evidence-session-type").value;
  const date = new Date(examAt);
  if (!sessionType) {
    toast("Choose whether this is a CAT, coursework, practical, final or special examination.", "error");
    return;
  }
  if (!examAt || Number.isNaN(date.getTime())) {
    toast("Choose a valid examination date and time.", "error");
    return;
  }
  try {
    const result = await api("/api/evidence/sessions", {
      method: "POST",
      body: JSON.stringify({
        assessment_id: $("#evidence-assessment").value,
        exam_at: date.toISOString(),
        venue: $("#evidence-venue").value.trim(),
        session_type: sessionType
      })
    });
    state.evidenceSelectedSession = result.session_id;
    $("#evidence-venue").value = "";
    $("#evidence-session-type").value = "";
    toast("Examination session created with " + result.candidate_count + " candidates.");
    await loadEvidenceAssessment(state.evidenceSelectedAssessment);
    await loadEvidenceSession(result.session_id);
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#evidence-cases-refresh").addEventListener("click", async () => {
  try {
    await loadEvidenceCases();
    toast("Evidence case queue refreshed.");
  } catch (error) {
    toast(error.message, "error");
  }
});

$("#evidence-refresh").addEventListener("click", async () => {
  try {
    await loadEvidence();
    toast("Assessment evidence refreshed.");
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── View loader ──────────────────────────────────────────────
async function loadCurrentView() {
  try {
    if (state.user.role === "student") await loadStudent();
    if (state.user.role === "lecturer") await loadLecturer();
    if (state.user.role === "reviewer") await loadReviewer();
    if (state.user.role === "exam_office") await loadExamOffice();
    if (state.user.role === "senate_office") await loadSenate();
    if (state.user.role === "portal_operator") await loadPortalOperator();
    if (state.user.role === "admin") await loadAdmin();
    if (state.navView === "evidence") await loadEvidence();
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
      $("#public-site").classList.add("hidden");
      $("#login-screen").classList.add("hidden");
      $("#password-change-screen").classList.remove("hidden");
      $("#pw-current").value = "";
      $("#pw-new").value = "";
      $("#pw-confirm").value = "";
      return;
    }

    $("#public-site").classList.add("hidden");
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
    $("#public-site").classList.add("hidden");
    $("#login-screen").classList.add("hidden");
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
    const message = result.on_chain
      ? "The saved record matches the verified blockchain copy."
      : result.match
        ? "The saved marks match the local commitment, but there is no independent blockchain copy."
        : "The saved record could not be verified. Review the batch status.";
    toast(message, result.match ? "success" : "error");
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
      body: JSON.stringify({
        name: data.name,
        max_mark: data.max_mark,
        submission_deadline: data.submission_deadline || null,
        release_policy: data.release_policy
      })
    });
    event.target.reset();
    toast("Assessment created with " + (data.release_policy === "SENATE" ? "Senate approval required." : "direct release.") );
    await loadAdmin();
  } catch (error) {
    toast(error.message, "error");
  }
});

// ── Administrator evidence rescan ───────────────────────────
document.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) return;

  const analyseButton = event.target.closest("[data-analyse-document]");
  if (analyseButton) {
    if (!["admin", "reviewer", "exam_office", "lecturer"].includes(state.user?.role)) {
      toast("Document extraction is available to assigned academic staff only.", "error");
      return;
    }
    const attachmentId = analyseButton.dataset.analyseDocument;
    if (!attachmentId) return;
    analyseButton.disabled = true;
    try {
      const result = await api(
        "/api/evidence/attachments/" + encodeURIComponent(attachmentId) + "/analyze",
        { method: "POST" }
      );
      state.evidenceDocumentAnalyses[attachmentId] = result;
      const row = analyseButton.closest("[data-attachment-row]");
      const previous = row?.nextElementSibling;
      if (previous?.matches("[data-document-analysis]")) previous.remove();
      row?.insertAdjacentHTML("afterend", renderEvidenceDocumentAnalysis(attachmentId, result));
      toast(
        result.status === "UNAVAILABLE"
          ? "Local OCR is not installed or configured on this host."
          : result.status === "FAILED"
            ? "Document extraction failed; the original file is unchanged."
            : "Text extracted. Review every suggestion against the original document.",
        result.status === "COMPLETE" || result.status === "PARTIAL" ? "success" : "error"
      );
    } catch (error) {
      toast(error.message, "error");
    } finally {
      analyseButton.disabled = false;
    }
    return;
  }

  const button = event.target.closest("[data-rescan-attachment]");
  if (!button) return;
  if (state.user?.role !== "admin") {
    toast("Only administrators can rescan quarantined evidence.", "error");
    return;
  }
  const attachmentId = button.dataset.rescanAttachment;
  if (!attachmentId) return;
  button.disabled = true;
  try {
    const result = await api(
      "/api/admin/evidence-attachments/" + encodeURIComponent(attachmentId) + "/rescan",
      { method: "POST" }
    );
    toast(
      result.scan_status === "CLEAN"
        ? "Evidence rescanned clean. Download is now available."
        : "Evidence remains blocked: " + result.scan_status.replaceAll("_", " ").toLowerCase() + ".",
      result.scan_status === "CLEAN" ? "success" : "error"
    );
    await loadCurrentView();
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
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
function openLoginScreen() {
  $("#public-site").classList.add("hidden");
  $("#login-screen").classList.remove("hidden");
  $("#login-username").focus();
}

function returnToPublicSite() {
  $("#login-screen").classList.add("hidden");
  $("#public-site").classList.remove("hidden");
}

document.querySelectorAll("[data-open-login]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    openLoginScreen();
  });
});

document.querySelectorAll("[data-back-to-site]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    returnToPublicSite();
  });
});

document.querySelectorAll(".site-mobile-nav nav a").forEach((link) => {
  link.addEventListener("click", () => {
    const menu = link.closest("details");
    if (menu) menu.open = false;
  });
});

const siteYear = $("#site-year");
if (siteYear) siteYear.textContent = String(new Date().getFullYear());

// ── Boot ─────────────────────────────────────────────────────
async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;

    if (me.must_change_password) {
      $("#public-site").classList.add("hidden");
      $("#login-screen").classList.add("hidden");
      $("#password-change-screen").classList.remove("hidden");
      return;
    }

    $("#public-site").classList.add("hidden");
    $("#login-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await loadDashboard();
    await loadCurrentView();
  } catch {
    $("#public-site").classList.remove("hidden");
    $("#login-screen").classList.add("hidden");
    $("#password-change-screen").classList.add("hidden");
    $("#app-shell").classList.add("hidden");
  }
}

boot();
