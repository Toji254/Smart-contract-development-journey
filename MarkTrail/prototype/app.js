const state = {
  student: {
    id: "STU-104",
    name: "Jane Doe",
    course: "CSC 201",
    assessments: [
      { id: "cat1", name: "CAT 1", mark: 18, max: 20, status: "submitted" },
      { id: "cat2", name: "CAT 2", mark: null, max: 20, status: "missing" },
      { id: "exam", name: "Final Exam", mark: 47, max: 60, status: "submitted" }
    ]
  },
  reports: [
    {
      id: "R-001",
      studentId: "STU-104",
      studentName: "Jane Doe",
      course: "CSC 201",
      assessmentId: "cat2",
      assessment: "CAT 2",
      status: "Open",
      openedAt: "8 Oct 2026 · 19:42"
    }
  ],
  audit: [
    {
      title: "CAT 2 batch submitted",
      detail: "87 student records committed by the lecturer.",
      time: "3 Oct 2026 · 10:32"
    },
    {
      title: "CAT 2 batch verified",
      detail: "Department reviewer approved the submitted batch.",
      time: "4 Oct 2026 · 09:18"
    }
  ]
};

const tabs = document.querySelectorAll(".tab");
const views = document.querySelectorAll(".view");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.remove("active"));
    views.forEach((view) => view.classList.remove("active"));

    tab.classList.add("active");
    document
      .getElementById(tab.dataset.view + "-view")
      .classList.add("active");

    render();
  });
});

function openReports() {
  return state.reports.filter((report) => report.status === "Open").length;
}

function renderStudent() {
  const submitted = state.student.assessments.filter(
    (assessment) => assessment.status === "submitted"
  ).length;

  const missing = state.student.assessments.length - submitted;

  document.getElementById("student-summary").innerHTML = `
    <div class="summary-card">
      <span class="mini-label">ASSESSMENTS</span>
      <strong>${state.student.assessments.length}</strong>
      <span class="muted">tracked</span>
    </div>
    <div class="summary-card">
      <span class="mini-label">SUBMITTED</span>
      <strong>${submitted}</strong>
      <span class="muted">available now</span>
    </div>
    <div class="summary-card">
      <span class="mini-label">MISSING</span>
      <strong>${missing}</strong>
      <span class="muted">needs attention</span>
    </div>
  `;

  document.getElementById("student-assessments").innerHTML =
    state.student.assessments
      .map((assessment) => {
        const existingReport = state.reports.find(
          (report) =>
            report.studentId === state.student.id &&
            report.assessmentId === assessment.id &&
            report.status === "Open"
        );

        const markText =
          assessment.mark === null
            ? "—"
            : `${assessment.mark}/${assessment.max}`;

        const action =
          assessment.status === "missing"
            ? existingReport
              ? `<span class="badge done">Reported</span>`
              : `<button class="primary" data-report="${assessment.id}">Report missing mark</button>`
            : `<span class="badge ok">Available</span>`;

        return `
          <article class="assessment-card">
            <div class="card-top">
              <div>
                <div class="assessment-title">${assessment.name}</div>
                <div class="muted">CSC 201</div>
              </div>
              <div class="grade">${markText}</div>
            </div>
            <div class="card-bottom">
              <div>
                <span class="badge ${assessment.status === "missing" ? "warn" : "ok"}">
                  ${assessment.status === "missing" ? "Missing" : "Submitted"}
                </span>
              </div>
              <div>${action}</div>
            </div>
          </article>
        `;
      })
      .join("");

  document.querySelectorAll("[data-report]").forEach((button) => {
    button.addEventListener("click", () => reportMissingMark(button.dataset.report));
  });
}

function renderLecturer() {
  const count = openReports();
  document.getElementById("open-count").textContent =
    `${count} open issue${count === 1 ? "" : "s"}`;

  const queue = document.getElementById("lecturer-queue");

  const open = state.reports.filter((report) => report.status === "Open");

  if (open.length === 0) {
    queue.innerHTML = `
      <div class="assessment-card">
        <strong>No open missing-mark reports.</strong>
        <p class="muted">The lecturer queue is clear.</p>
      </div>
    `;
    return;
  }

  queue.innerHTML = open
    .map(
      (report) => `
        <article class="issue-card">
          <div class="issue-main">
            <div>
              <div class="issue-title">${report.studentName} · ${report.studentId}</div>
              <div class="muted">${report.course} · ${report.assessment}</div>
            </div>
            <span class="badge warn">Open</span>
          </div>

          <p class="muted">Reported ${report.openedAt}</p>

          <div class="actions">
            <button class="primary" data-resolve="${report.id}">Resolve with mark</button>
            <button class="secondary" data-no-mark="${report.id}">No mark awarded</button>
          </div>
        </article>
      `
    )
    .join("");

  document.querySelectorAll("[data-resolve]").forEach((button) => {
    button.addEventListener("click", () => resolveWithMark(button.dataset.resolve));
  });

  document.querySelectorAll("[data-no-mark]").forEach((button) => {
    button.addEventListener("click", () => resolveNoMark(button.dataset.noMark));
  });
}

async function renderAudit() {
  document.getElementById("audit-timeline").innerHTML = state.audit
    .slice()
    .reverse()
    .map(
      (entry) => `
        <div class="timeline-item">
          <strong>${entry.title}</strong>
          <span>${entry.detail}</span>
          <small>${entry.time}</small>
        </div>
      `
    )
    .join("");

  const payload = JSON.stringify(
    state.student.assessments.map(({ id, mark, max, status }) => ({
      id,
      mark,
      max,
      status
    }))
  );

  document.getElementById("demo-hash").textContent = await sha256(payload);
}

function reportMissingMark(assessmentId) {
  const assessment = state.student.assessments.find(
    (item) => item.id === assessmentId
  );

  if (!assessment || assessment.status !== "missing") return;

  state.reports.push({
    id: `R-${String(state.reports.length + 1).padStart(3, "0")}`,
    studentId: state.student.id,
    studentName: state.student.name,
    course: state.student.course,
    assessmentId,
    assessment: assessment.name,
    status: "Open",
    openedAt: "just now"
  });

  state.audit.push({
    title: `${assessment.name} missing-mark report opened`,
    detail: `${state.student.id} created a traceable issue.`,
    time: "just now"
  });

  render();
}

function resolveWithMark(reportId) {
  const report = state.reports.find((item) => item.id === reportId);
  if (!report) return;

  const raw = window.prompt(
    `Enter the mark for ${report.studentName} (${report.assessment}):`,
    "17"
  );

  if (raw === null) return;

  const mark = Number(raw);
  const assessment = state.student.assessments.find(
    (item) => item.id === report.assessmentId
  );

  if (!assessment || !Number.isFinite(mark) || mark < 0 || mark > assessment.max) {
    window.alert(`Enter a mark from 0 to ${assessment.max}.`);
    return;
  }

  assessment.mark = mark;
  assessment.status = "submitted";
  report.status = "Resolved";
  report.resolvedAt = "just now";

  state.audit.push({
    title: `${report.assessment} amended`,
    detail: `${report.studentId} received ${mark}/${assessment.max}; previous missing state preserved in the timeline.`,
    time: "just now"
  });

  render();
}

function resolveNoMark(reportId) {
  const report = state.reports.find((item) => item.id === reportId);
  if (!report) return;

  const assessment = state.student.assessments.find(
    (item) => item.id === report.assessmentId
  );

  report.status = "Resolved";
  report.resolvedAt = "just now";

  if (assessment) {
    assessment.status = "submitted";
    assessment.mark = 0;
  }

  state.audit.push({
    title: `${report.assessment} report resolved`,
    detail: `${report.studentId} was confirmed as having no awarded mark.`,
    time: "just now"
  });

  render();
}

async function sha256(input) {
  if (window.crypto?.subtle) {
    const data = new TextEncoder().encode(input);
    const hash = await window.crypto.subtle.digest("SHA-256", data);
    return (
      "0x" +
      Array.from(new Uint8Array(hash))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("")
    );
  }

  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }

  return "demo-" + Math.abs(hash).toString(16);
}

function render() {
  renderStudent();
  renderLecturer();
  renderAudit();
}

render();
