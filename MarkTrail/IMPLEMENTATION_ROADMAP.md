# MarkTrail delivery roadmap — Karatina University pilot

Version: 1.0  
Status: active build plan  
Working branch: agent-copy/marktrail-z2  
Product goal: prevent avoidable missing marks, localise unavoidable exceptions quickly, and give students and staff a fair, traceable route to resolution.

## Product decision

MarkTrail is an assessment-evidence and academic-record workflow platform. It is not a blockchain marks database and it is not an AI adjudicator.

The primary record is an institution-governed academic workflow in which every expected candidate and assessment component has an explicit, reviewable state. Actual student identity, marks, scripts, attendance evidence, medical/deferred-exam evidence and investigation notes remain in protected off-chain storage.

The existing Karatina examination requirements for a valid examination card and a signed examination attendance register are supported as source evidence. Digital records supplement the approved university process; this product must not unilaterally replace university rules, official examination forms, the student portal or Senate approval.

## Operating model

An academic unit may contain several independent components:
- CAT 1, CAT 2, CAT 3 or other continuous assessment.
- Practical, laboratory, project or coursework assessment.
- Main examination.
- Special, supplementary or deferred examination where institutionally authorised.

Each component has its own maximum mark, weighting, candidate/eligibility snapshot, source evidence, marks submission, review and publication state. The final grade calculation and result release must follow the university's approved rules. The software must never assume that all components are present or that every final result follows the same publication timetable.

## Workstreams and delivery gates

### Gate 0 — Karatina policy and process validation

Purpose: prevent incorrect assumptions from becoming software rules.

Deliverables:
- Approved process map for registration, CAT capture, exam-card issue, attendance, script collection, marking, moderation, departmental review, exam-office processing, Senate approval and portal publication.
- Approved forms/templates and data dictionaries, including exam card, attendance register, script packet/receipt, marks sheet, marks-return sheet, missing-mark request, special/deferred examination approval and portal import template.
- Role/authority matrix showing who may create, record, review, approve, amend, release and investigate.
- Configurable service-level targets and escalation points for each handoff.
- Data Protection Impact Assessment and institution-approved data-retention schedule.
- Interviews/observation with students, lecturers, invigilators, HOD/school examination coordinators, exam-office staff, Senate/Academic Registrar representatives and ICT/portal administrators.

Exit criteria:
- No workflow gate is coded as an official Karatina rule until it is validated by an authorised institutional representative.
- The university approves the first pilot scope and its relationship to official systems.
- No live student data is used before lawful basis, access controls, privacy review and pilot authorisation are established.

### Gate 1 — Assessment and roster foundation

Deliverables:
- Academic year, semester, programme, course offering and unit records.
- Assessment definitions with component type, max mark, weighting, exam mode, scheduled date, deadline, responsible lecturer/marker and approval profile.
- Enrolment snapshot and version history for every assessment.
- Explicit add/drop, late-registration, transfer and approved-exception events.
- Candidate eligibility snapshot for each final examination session.
- Import validation for registration numbers, duplicates, unregistered candidates, inactive/withdrawn students and ambiguous identities.

Exit criteria:
- Every expected candidate is represented in an assessment roster snapshot.
- Roster changes preserve the original version, actor, reason and approval.
- Registration mismatch is an exception requiring authorised resolution, not an automatic mark or automatic absence.

### Gate 2 — Examination evidence ledger

Current implementation slice:
- Database-backed examination sessions linked to existing assessment records.
- Locked candidate roster snapshot.
- Per-candidate attendance decision: PRESENT, ABSENT, EXCUSED or CONTESTED.
- Recorded signature, examination-card and student-ID checks.
- Script receipts with unique session reference.
- Script custody handover request and explicit receiver acceptance.
- Marking-completion event, without placing mark values in the custody event.
- Unidentified script quarantine and reviewer/exam-office identity-link action with a distinct IDENTITY_LINKED event.
- Deterministic reconciliation exceptions for missing attendance, missing signature, missing card/ID check, signed-but-recorded-absent conflict, absent/script conflict, present/no-script, unaccepted custody, unmarked script and marked/no-mark-entry.
- Persistent evidence cases automatically opened from detected exceptions and keyed by session plus candidate/script plus category.
- Case ownership routed to the course lecturer, exam office or reviewer; staff queues are role-scoped and show the named owner plus append-only action history.
- Evidence corrections move a case to EVIDENCE_CLEARED, not automatically resolved; a reviewer/admin must explicitly resolve or dismiss with a reason.
- A previously cleared and resolved/dismissed exception reopens if the same discrepancy reappears; the prior decision remains in case history.
- Student and assigned-staff notifications for case opening, evidence clearing, reopening and final decisions.
- Append-only session, attendance, script-custody and evidence-case chronology, including correction reasons and ownership events.
- Closed attendance register; reviewer/admin correction requires a written reason and leaves an audit event.
- Student-scoped read-only exam-progress and case-status API/view; it omits staff-only notes, script references, assignments and decision rationale.
- Role-scoped API and responsive staff/student workspaces.

Remaining work in this gate:
- Attachments/scans of approved source records with encrypted object storage and a hash linked to the evidence event.
- Packet-level script bundles and invigilator-to-department handover manifests.
- Multi-marker/team-teaching assignments and explicit marking handovers.
- Script loss/damage/illegible identifier incident handling and controlled recovery.
- Candidate identity resolution with dual approval for high-risk matches.
- Bulk attendance import from approved paper-register transcription files, including row-level provenance and operator attribution; current bulk save is for manual workspace capture.
- Offline capture queue with conflict detection and safe synchronisation.
- Student-facing appeals and evidence-submission workflow beyond the current read-only case status and neutral notifications, without exposing staff-only notes or personal data of other candidates.
- Configurable case service-level deadlines, escalation rules and workload analytics; current ownership is role/user based but has no Karatina-approved SLA schedule.

Exit criteria:
- Every candidate has an explicit attendance decision before a register can be closed.
- A missing signature is never equated with absence.
- An attended candidate without a script creates a visible exception.
- A script for a recorded absent candidate creates a conflict.
- Every script has a traceable custodian and handover acceptance.
- A marked script without a submitted mark is visible as an exception.
- Corrections append history; no staff member can silently rewrite prior attendance or custody evidence.

### Gate 3 — Marks submission and completeness engine

Deliverables:
- Component-specific capture and CSV import for each CAT and final assessment.
- Canonical roster join by institutional registration number and internal student ID, not spreadsheet row order.
- Support for numeric mark and approved non-numeric outcomes: ABSENT, NOT_SUBMITTED, EXCUSED, DEFERRED, WITHHELD_PENDING_PROCESS, NOT_APPLICABLE and other institution-approved codes.
- Configurable validation of maximum marks, decimal precision, component weighting, required rows, duplicate registrations, unregistered students and unexplained omissions.
- Preview showing included, omitted, duplicated, invalid and exception candidates before submission.
- Explicit "no mark awarded" outcome requiring authorised reason and supporting evidence where policy requires.
- Durable submission receipt, idempotency key, operation status and safe retry after network failure.
- Lecturer workload/overdue dashboard and reassignment/handover for departed or unavailable staff.

Exit criteria:
- An incomplete batch cannot be submitted unless every missing candidate has an allowed, explicit, reason-coded outcome.
- Retrying a timed-out submission cannot create a duplicate batch or overwrite an existing batch.
- A lecturer can prove which exact batch version was submitted and when it was received.

### Gate 4 — Review, exam-office, Senate and portal governance

Deliverables:
- Departmental reviewer queue with row-level exceptions and approve/reject/return-with-reason decisions.
- Separation of duties: reviewers approve; they do not silently edit lecturer marks.
- Exam-office queue with accepted/rejected states and processing acknowledgement.
- Configurable Senate/Academic Board approval gate for final results, with meeting/decision reference, approved batch revision, approver identities and timestamp.
- Separate publication rules for CATs, coursework and final results.
- Portal import adapter with dry-run, file/API acknowledgement, imported row count, rejection details and batch-to-portal reconciliation.
- Result visibility rules: provisional/under review/awaiting Senate/approved awaiting portal import/published.
- Controlled correction/republication process requiring reason, authority and a new immutable revision.
- Historical portal import reconciliation and stuck-work escalation.

Exit criteria:
- A final result cannot be shown as official before required Senate approval and portal publication.
- CAT release can occur independently if institutional rules permit.
- A portal mismatch is routed to ICT/portal operations, not incorrectly back to the lecturer.
- Every handoff has a durable receiver acknowledgement or an explicit failure/exception state.

### Gate 5 — Student support and appeals

Deliverables:
- Student self-service component-by-component progress view.
- One report per candidate/assessment issue, with duplicate linking rather than duplicate cases.
- Student evidence upload with file-type/size validation and privacy-safe storage.
- Clear case number, owner office, current stage, next update target and appeal/escalation route.
- Status messages written in clear language; never display confidential staff notes or another candidate's information.
- Case categories separating registration, attendance, script, marking, submission, review, Senate, portal and formal-investigation issues.
- Case state machine: OPEN, TRIAGED, EVIDENCE_GATHERING, ACTION_REQUIRED, RESOLUTION_PROPOSED, REVIEW_REQUIRED, RESOLVED, NOT_A_MISSING_MARK, DUPLICATE_CASE, REFERRED_FOR_FORMAL_INVESTIGATION.
- Reopen/review path preserving previous decisions and evidence.
- Service-level clock pauses only for explicitly defined reasons and remains visible to authorised staff.

Exit criteria:
- A student can report once and track the issue without visiting several offices to discover who owns it.
- Students can challenge incorrect records and request human reconsideration.
- Case resolution never changes official marks without the relevant academic authority and approval path.

### Gate 6 — Deterministic reconciliation and AI copilot

Build deterministic reconciliation first. AI is added only after reliable structured data exists.

Rules engine deliverables:
- Compare approved registration snapshot, exam eligibility, attendance, script receipts, marking status, marks batch, review decisions, Senate decisions and portal rows.
- Emit reason-coded exceptions with source record IDs and exact mismatches.
- Detect scripts that lack attendance, present candidates without scripts, scripts not marked, marks omitted from a batch, marks for recorded absentees, batches awaiting approval and portal mismatches.
- Expose ruleset version and run timestamp so a reconciliation result is reproducible.

AI copilot deliverables:
- Summarise a case chronology from approved internal events.
- Suggest likely failure stage and missing evidence, citing internal record IDs.
- Detect duplicate/near-duplicate registration number or name candidates for human review.
- Prioritise cases based on objective urgency, graduation/registration deadline and case age; allow staff override.
- Detect unusual bulk changes, late amendments, repeated manual overrides and suspicious access patterns for investigation.
- Draft neutral student/staff communications and management reports.
- Explain why it flagged a case and disclose uncertainty.

Hard restrictions:
- AI cannot create, guess, fill, amend or approve a mark.
- AI cannot decide that a student was absent or did not submit a script.
- AI cannot reject an appeal, impose a penalty, accuse a person or release results.
- AI suggestions require a named human decision and reason.
- Conflicting, missing or low-confidence evidence must return UNCLASSIFIED / HUMAN_REVIEW_REQUIRED.
- Identifiable student data must not be sent to an external AI processor without institutional approval, a lawful basis, a documented data-processing arrangement and privacy safeguards.

Exit criteria:
- Every AI suggestion can be traced to source records and independently reproduced where possible.
- False-positive/false-negative rates are measured on institution-approved synthetic and pilot data.
- No academic outcome depends solely on AI processing.

### Gate 7 — Blockchain audit and institutional key custody

Current implementation:
- Existing MarkTrailAudit contract stores salted commitments for marks batches and append-only revision metadata.
- Actual marks and student identifiers remain off-chain.
- Application supports local-only operation and an optional EVM audit adapter.

Remaining deliverables:
- Canonical schema/version for batch payloads and domain-separated commitments.
- Random cryptographic salt per revision; secure off-chain storage of payload, salt and evidence snapshots.
- Anchor commitments for assessment roster version, submitted marks batch, reviewer approval, exam-office acknowledgement, Senate decision and portal import receipt where these events benefit from independent timestamping.
- Do not publish student identifiers, marks, scripts, personal data, document hashes that enable dictionary attacks, or sensitive investigation metadata on a public chain.
- Transaction intent/idempotency ledger, receipt monitoring, confirmation policy, reorg handling, failed/pending state, reconciliation and recovery playbooks.
- Institutional key custody, signing separation, rotation, access monitoring and incident response.
- Permissioned chain versus public chain decision based on governance, privacy, cost, public verifiability and sustainability.
- Independent smart-contract audit and fuzz/invariant tests before any production use.

Exit criteria:
- Chain downtime does not block student reports or local assessment capture.
- Local-only records are clearly distinguished from externally anchored records.
- Every amendment adds a new revision and never erases prior evidence.
- The chain is never represented as proof that an attendance record or academic mark is factually correct.

### Gate 8 — Security, privacy, accessibility and operational readiness

Deliverables:
- Institutional SSO/MFA, least-privilege access, role and course scope, account lifecycle, session security and privileged-action approvals.
- Threat model updated for data import, script scans, offline operation, staff collusion, compromised lecturer/admin accounts, malicious uploads and chain signer compromise.
- Encryption in transit and at rest; protected secrets; key rotation; audited backups and tested disaster recovery.
- File malware scanning, strict upload limits, type checking, safe export and spreadsheet formula-injection protection.
- Audit log integrity and monitoring; alerting for suspicious changes and access.
- Data minimisation, purpose limitation, retention/deletion schedule, rights handling, access logs, DPIA and processor/vendor assessments.
- Keyboard navigation, mobile responsive layouts, clear empty/error/loading states, accessible contrast, plain-language messages and Kenyan context support.
- Defined availability, RPO/RTO, support ownership, service-level targets and operational runbooks.

Exit criteria:
- Independent security review and privacy sign-off.
- Recovery test succeeds from backup.
- Accessibility and role-isolation tests pass.
- No production credentials or real student data in repository, local demo seed or public chain.

### Gate 9 — Controlled pilot and evaluation

Pilot approach:
1. Synthetic data and adversarial scenarios.
2. Staff usability test with blank/sample forms.
3. One approved department/unit pilot in parallel with official processes.
4. Compare every MarkTrail state with the official source system and signed paperwork.
5. Resolve pilot findings and obtain institutional sign-off before expanding.
6. Expand in stages; do not make MarkTrail the official source of academic records without written university approval.

Success metrics:
- Missing-mark cases per 1,000 candidate-assessment records.
- Percentage of assessment records with complete evidence before publication.
- Script custody gap count.
- Incomplete batches caught before submission.
- Percentage of handoffs with acknowledgement.
- Median and 90th percentile case-resolution time.
- Number of offices/contact attempts required per case.
- Percentage of portal imports that exactly match approved batches.
- Silent amendments (target zero).
- AI false positives and false negatives.
- Student/staff satisfaction and accessibility findings.

## Current build status

Implemented in this branch as an initial vertical slice:
- Assessment evidence service and idempotent table creation.
- Candidate snapshot at session creation.
- Explicit assessment/session classification: CAT, coursework, practical, final examination and special/deferred examination; legacy sessions migrate as UNCLASSIFIED rather than being guessed.
- Attendance status, signature, exam-card and student-ID evidence.
- Atomic bulk attendance capture with full payload validation and rollback on any invalid candidate; closed registers require individual reviewer/admin corrections with written reasons.
- Register closure requiring an explicit attendance decision for every candidate.
- Script receipt references, including quarantine for unidentified scripts and reviewer/exam-office candidate matching.
- Script custody handover request and recipient acceptance, with readable named custodians.
- Marking-completion tracking separate from numeric marks.
- Lecturer-in-charge physical exam-card sign-off for final/special examinations, after register closure and only when presence, signature, card check and linked script receipt reconcile; CATs do not require this gate.
- Append-only session, attendance, script-custody and physical exam-card sign-off event histories.
- Deterministic exceptions for attendance/signature conflicts, missing scripts, missing sign-offs, custody gaps and mark-entry mismatches.
- Authenticated evidence API and student-scoped read-only progress API.
- Staff evidence workspace with activity timeline, atomic bulk attendance, card-signoff controls and role-scoped persistent evidence case queue.
- Student exam-progress tab with privacy-safe case status and neutral notifications; staff receive assigned-case notifications.
- Case state transitions OPEN → EVIDENCE_CLEARED → RESOLVED/DISMISSED, with REOPENED events for recurring exceptions and immutable action history.
- Legacy SQLite migration for unidentified scripts, identity-link events and session type, preserving existing records.
- Dedicated regression tests for permissions, privacy, atomic updates, legacy migration, case ownership, human resolution and case reopening.

Not yet implemented or independently verified:
- Student-facing appeals, evidence-upload and case-progress improvements beyond the current read-only exam-progress view.
- Evidence document attachments, scan/OCR, bulk register import and offline sync.
- Team-teaching assignment and multi-marker support.
- Unit component types/weighting and full result calculation.
- End-to-end automated integration with Karatina's official student portal; the app has a local portal-operator publication stage but no approved university portal adapter.
- Configurable missing-mark case SLAs, escalation policy and institutional workload reporting beyond current role/user assignment and reviewer decisions.
- Deterministic cross-system reconciliation across all workflow evidence.
- AI copilot.
- Expanded blockchain event anchoring and production-grade signing custody.
- Institutional SSO, DPIA, independent security review, production hosting, backups and disaster recovery.
- Karatina's current internal process validation and pilot approval.
- CI verification for the newest evidence-case UI and backend integration commits, plus browser usability testing on the current branch build.

## Engineering rules

- Build local-only first; do not make a wallet or RPC endpoint mandatory for normal users.
- Preserve existing application data and workflows with explicit migrations.
- Every important action needs server-side authorisation; hiding a UI control is not security.
- Every state transition must be validated by the backend and written to audit history.
- No raw student data or marks on-chain.
- No silent data mutation, no invented marks, no automatic academic decisions.
- Prefer structured rule-based checks before AI.
- Each feature ships with tests for happy paths, permissions, duplicates, conflicting evidence, retries, failure recovery and historical compatibility.
- Keep each PR focused and record the exact tests and CI run that passed.
