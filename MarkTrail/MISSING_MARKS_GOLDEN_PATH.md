# MarkTrail: Missing-Marks Golden Path

Status: design baseline for the next implementation phase  
Target pilot: Karatina University-style semester assessment workflow  
Scope: CATs/coursework, final examinations, exam attendance, script custody, marks processing, Senate approval and student resolution

## 1. Product thesis

Missing marks are a failure of assessment-evidence continuity and workflow accountability. MarkTrail must be able to answer, for every student and every assessment component:

1. Was the student registered for the unit?
2. Was the student expected and eligible to sit this assessment?
3. What evidence exists that the student participated or did not participate?
4. Was a script or submission received, and who took custody?
5. Was it marked, moderated where required, and included in the submitted marks batch?
6. Who received, reviewed, approved, processed and published the result?
7. If any step failed, who owns the next action and by when?
8. If the record changed, what changed, why, who authorised it and which version is current?

The system must prevent avoidable omissions, detect gaps early, preserve evidence, make case ownership visible and provide a fair route to resolution. Blockchain is an integrity layer, not the source of truth for whether a student attended or earned a mark.

## 2. Root-cause model

Treat these as failure classes to investigate, not as accusations against any particular person:

- Identity and enrolment: wrong registration number, name mismatch, duplicate student, wrong semester, unit not registered, late/approved registration correction.
- Assessment capture: CAT attendance not recorded, marks on paper but not in the spreadsheet, missing CAT component, duplicate or omitted rows, incorrect maximum/weight.
- Exam eligibility and logistics: exam card mismatch, student absent from official attendance register, room/register mismatch, approved special/deferred exam not reflected.
- Attendance and script evidence: student signs but does not hand in a booklet; student submits but signature is omitted; script has no usable identifier; booklet is lost; attendance sheet or script packet is misplaced.
- Marking and custody: unrecorded handover between team lecturers, unassigned scripts, unmarked scripts, delayed marking, staff departure, unclear custody.
- Transcription and submission: spreadsheet errors, wrong row alignment, manual re-keying, incomplete batch, unacknowledged email/USB handoff, lecturer fails to submit.
- Review and publication: department/exam-office queue backlog, failed import, rejected batch not returned to owner, result held for moderation or Senate approval, portal publishing mismatch.
- Technology and governance: network outage, duplicate retries, weak backups, excessive permissions, shared accounts, no audit review, policies not enforced, inadequate training or staffing.
- Deliberate wrongdoing: intentional withholding, unauthorised alteration, collusion or falsification. These require due process and independent investigation; anomaly detection is not proof.

## 3. Competing strategic branches and decision

| Approach | Strength | Weakness | Decision |
|---|---|---|---|
| Digitise cards/registers/sheets | Removes illegibility and makes evidence searchable | Digitising a weak process does not enforce handoffs | Adopt as evidence capture |
| Workflow and deadline enforcement | Makes every stage, owner, acknowledgement and exception visible | Requires institutional process ownership | Make this the core |
| Blockchain audit | Makes committed versions and later changes independently verifiable | Cannot validate truth of source data; privacy and key custody risks | Use narrowly for batch commitments |
| AI reconciliation | Finds anomalies and predicts bottlenecks early | Can be wrong, biased or overconfident | Use as decision support only |
| Student transparency and appeals | Reduces anxiety and exposes unresolved cases | Student claims alone do not prove attendance or marks | Adopt with privacy and human review |

Golden path: **workflow-first, evidence-backed, privacy-preserving, blockchain-anchored, AI-assisted, human-governed**.

## 4. Canonical assessment lifecycle

Every unit is a parent record. Every CAT, coursework component, practical, final examination or special examination is a distinct assessment instance with its own roster, maximum mark, weighting, dates, evidence and status.

Suggested lifecycle:

1. Unit offering and enrolment snapshot locked for the assessment period.
2. Assessment created with component type, weight, maximum mark, schedule, responsible lecturer and required approval path.
3. Eligible candidate list generated from the approved registration snapshot. Corrections are explicit, authorised events; never silently rewrite the original snapshot.
4. CAT/coursework participation and marks captured. Each upload is validated against the roster and receives an import receipt.
5. Final exam eligibility snapshot generated from institutional rules and approved exceptions.
6. Invigilator records attendance, incident/exception details and candidate signatures. A missing signature creates an exception, not an automatic absent verdict.
7. Script/booklet collection reconciled against candidates present. Each script packet receives a batch/packet identifier and custody handover.
8. Marking assignment created. Script received, marked, moderated (where required), and marks entered with source reference.
9. Lecturer previews the complete component batch; system blocks invalid marks, duplicate identities, missing expected rows and unexplained omissions. Explicit outcomes such as absent, not submitted, approved special exam, withheld pending investigation or not applicable must be separate from numeric marks.
10. Lecturer submits and receives a durable receipt containing batch ID, row count, assessment ID, content commitment, timestamp and current workflow state.
11. Department reviewer checks exceptions, completeness and policy compliance. Reviewer cannot silently edit marks.
12. Exam office processes the approved batch and records acceptance/rejection with reason.
13. Senate approval is represented as a formal gate for final results, according to the institution's actual governance rules. CAT visibility and final-exam/final-grade publication permissions are configurable separately.
14. Portal operator imports the approved result and records import receipt, row counts and reconciliation outcome.
15. Student sees only what policy permits: CAT marks where released; for final results, a neutral status such as "submitted / under review / awaiting approval / approved but not yet published" until official release.
16. Reconciliation continuously compares expected records, evidence, marks, approvals and portal state. Any gap opens or updates a case.

No step should be considered complete merely because a user clicked a button. It must have a durable acknowledgement or independently verifiable evidence.

## 5. Evidence model

Evidence should be recorded as separate linked events, not collapsed into one editable status field.

Core entities:
- Student (institutional identifier; minimal personal data)
- UnitOffering (unit, semester, academic year, school, programme)
- EnrolmentSnapshot (approved registration state and version)
- Assessment (CAT 1/2/3, coursework, practical, final, special exam)
- CandidateEligibilitySnapshot
- AttendanceSession and AttendanceEntry
- ExamIncident (late arrival, register omission, booklet issue, approved exception)
- ScriptPacket and ScriptCustodyEvent
- MarkingAssignment and MarkEntry
- MarksBatch and MarksBatchRevision
- ReviewDecision, ExamOfficeDecision, SenateDecision, PortalImportReceipt
- MissingMarkCase, EvidenceAttachment, CaseAction, Resolution
- AuditEvent and Notification

Each event should include a unique ID, actor identity, actor role, timestamp, source channel, related assessment/student/batch IDs, action, previous state, new state, reason where applicable, and evidence references. Store event time in UTC plus the institution's local display timezone. Preserve original uploaded files and their hashes; do not rely on a hash as a substitute for the original evidence.

### Evidence strength is contextual

- Signed attendance register: evidence of a signature, not conclusive proof of script submission or completion.
- Script collected and linked to candidate: strong evidence of submission, but not proof of correct marking.
- Invigilator incident report: corroborating evidence, subject to review.
- Lecturer's marks sheet: evidence of an entered score, not necessarily proof that the score was correctly transcribed or approved.
- Submission receipt: proof that a specific batch was received, not proof that its contents are correct.
- Blockchain commitment: proof that a specific committed representation existed by a certain chain event, not proof that the underlying representation was truthful.

Never automatically turn absence of one evidence item into a disciplinary finding or a zero mark.

## 6. Missing-mark classification and case workflow

Use explicit case categories:
- NOT_REGISTERED_OR_REGISTRATION_MISMATCH
- CAT_COMPONENT_MISSING
- ATTENDANCE_SIGNATURE_MISSING
- ATTENDANCE_CONFLICT
- SCRIPT_NOT_RECEIVED
- SCRIPT_UNIDENTIFIED
- SCRIPT_CUSTODY_GAP
- SCRIPT_NOT_MARKED
- MARK_NOT_ENTERED
- MARKS_BATCH_OMISSION
- SUBMISSION_NOT_ACKNOWLEDGED
- REVIEW_PENDING
- EXAM_OFFICE_PENDING
- SENATE_PENDING
- PORTAL_IMPORT_MISMATCH
- APPROVED_SPECIAL_OR_DEFERRED_EXAM
- TECHNICAL_OR_DATA_INTEGRITY_FAILURE
- POSSIBLE_MISCONDUCT_REQUIRES_INVESTIGATION
- UNCLASSIFIED

Case states:
OPEN -> TRIAGED -> EVIDENCE_GATHERING -> ACTION_REQUIRED -> RESOLUTION_PROPOSED -> REVIEW_REQUIRED -> RESOLVED
Alternative terminal states: NOT_A_MISSING_MARK (with reason and appeal route), DUPLICATE_CASE (linked to canonical case), or REFERRED_FOR_FORMAL_INVESTIGATION. Reopening must preserve the previous resolution and create a new case action.

Every open case has one accountable owner, a due date, next action, escalation route and student-visible status. Do not expose confidential staff notes or disciplinary details to students.

A numeric mark can only be entered or amended by an authorised academic actor under the institution's rules. A reviewer can approve/reject, not secretly rewrite. An exam office can process, not invent. A portal operator can import, not alter. A student can report and submit evidence, not edit the academic record.

## 7. Blockchain boundary

Keep actual marks, student names, registration numbers, scripts, attendance images, incident notes and personal data off-chain.

For each batch revision:
- Canonicalise a deterministic payload including assessment ID, roster version, component identifiers, row identifiers and marks/outcome codes.
- Generate a cryptographically secure random salt per revision.
- Compute a domain-separated commitment using a well-reviewed scheme and canonical encoding.
- Store the payload, salt and source evidence in protected off-chain storage with access controls and backups.
- Anchor only non-identifying batch metadata and commitment on-chain.
- Record the chain transaction hash, block number, contract address and confirmation state.
- Verify the off-chain payload against the commitment before publication and during reconciliation.
- Append new revisions; never overwrite or delete the prior revision.
- Keep a durable transaction intent/idempotency key so a timeout never triggers a blind duplicate transaction.

A permissioned institutional EVM or a public chain can be evaluated later. The first local pilot should run LOCAL_ONLY with explicit labels that it has no independent chain anchor. Blockchain must never be a hard dependency for a student reporting a case or a lecturer capturing a mark during a network outage.

The current contract is a batch commitment/revision prototype. It does not yet represent attendance, script custody, individual case evidence, Senate decisions or portal import. Do not pretend it does.

## 8. AI boundary

AI is a staff copilot and anomaly detector, never an academic decision-maker.

Useful AI tasks:
- Compare registration, attendance, script receipt, marking and marks-batch rosters to suggest likely omission points.
- Flag duplicate/near-duplicate registration numbers, name mismatches, out-of-range marks, missing CAT components and inconsistent row counts.
- Prioritise cases by graduation impact, deadline and evidence completeness.
- Summarise a case timeline and list missing evidence or next responsible office.
- Detect unusual bulk changes, late amendments, repeated manual overrides or suspicious access patterns for human review.
- Draft neutral student updates and staff requests for evidence.
- Produce workload and bottleneck reports by stage, without publicly ranking or shaming staff.

AI must return structured suggestions with reasons, supporting record IDs and confidence/uncertainty. Every suggestion must be reviewable. Low confidence or conflicting evidence means UNCLASSIFIED / HUMAN_REVIEW_REQUIRED. AI must not generate marks, infer an absent student, approve a result, reject an appeal, accuse a lecturer/student, or publish results. Do not send identifiable student data to third-party AI services without a lawful basis, institutional approval, data-processing safeguards and privacy review.

## 9. Persona tabletop competition

These are adversarial test scenarios, not claims about actual Karatina incidents. The system passes only if it treats each persona fairly and produces a traceable outcome.

| Persona / scenario | What they say or do | System response | Must not happen |
|---|---|---|---|
| Student sat exam; signed; mark missing | Reports anxiety and provides unit/exam period | Show case ID and status; correlate signature, script receipt, marking and batch records; route to the exact broken stage | Tell student to chase several offices; assume lecturer negligence |
| Student sat exam; signature omitted | Says invigilator allowed them to sit | Flag attendance conflict; collect seating, incident, script and invigilator evidence; human review | Automatically mark absent or award marks |
| Student signed but left without submitting booklet | Claims they sat the paper | Compare attendance with script collection; investigate incident and rules; authorised academic decision | Treat signature as proof of completed script |
| Student did not sit and has no approved special exam | Requests a mark after results release | Explain the recorded status and formal appeal/special-exam route | Manufacture a mark or allow staff to quietly fill one |
| Student missed exam due to approved medical/special circumstance | Has approval but system shows absent | Match approved exception to exam and update eligibility/outcome through authorised workflow | Force the student to prove the same approval repeatedly |
| Student was not registered but attended | Registration snapshot conflicts with attendance/script | Route to registration/academic office for formal eligibility decision | Lecturer silently adds student to roster |
| Student has wrong registration number on script | Script may be present under a typo | Suggest candidate match using controlled identity fields; require human verification and evidence | AI automatically merge two students |
| Lecturer completed marks but forgot submission | Local sheet exists, no receipt | Alert lecturer before deadline; provide safe submit/resume and receipt | Treat an unsubmitted spreadsheet as officially received |
| Part-time lecturer leaves or is unavailable | Unresolved marks remain | Preserve departmental custody, escalate to HOD/Dean, support authorised reassignment | Make a departed lecturer's account or key available to others |
| Team-taught unit | Script moves between markers | Require explicit custody/marking handoff and role-specific actions | Lose accountability between lecturers |
| Lecturer uploaded incomplete CSV | Several enrolled students omitted | Block or quarantine batch with row-level validation; allow explicit reason-coded outcomes | Accept silently or convert omissions to zero |
| Marks officer transposes two rows | Student A/B marks swapped | Detect source-to-import mismatch where source data available; require correction revision | Overwrite the previous version |
| Reviewer disagrees with lecturer | Reviewer rejects batch | Return with reason and evidence; preserve both versions and timestamps | Reviewer edits source marks without attribution |
| Exam office receives batch but import fails | Processing is stuck | Show received-but-not-imported state; retry idempotently; reconcile import receipt | Tell student result is published |
| Senate has not approved final results | CATs are visible but final marks are restricted | Show final-result approval status without revealing embargoed marks | Leak provisional final marks or mislabel them as final |
| Student's result was approved but portal omitted it | Official approved batch differs from portal | Open portal mismatch case with import row evidence; assign portal operator | Send student back to lecturer if the failure is downstream |
| Malicious staff account changes a mark | Unusual amendment after approval | Require reason, new revision, separation of duties, alert and investigation | Allow silent database update or AI-only accusation |
| Student files duplicate reports | Same assessment already has an open case | Link duplicate to canonical case; preserve messages and evidence | Lose the student's report or create conflicting resolutions |
| Network/chain unavailable | Lecturer submits during outage | Save a durable local submission intent, clearly label unanchored state, queue safe retry and reconcile | Lose the batch or claim chain confirmation |
| AI flags a suspicious pattern incorrectly | Staff challenge the flag | Show the records and rationale; permit dismissal with reason and monitor false positives | Punish a student/lecturer based on model output |

## 10. Privacy, security and governance

- Apply Kenya's Data Protection Act and ODPC education-sector guidance: lawful purpose, transparency, data minimisation, accuracy, retention limits, access controls, data-subject rights, privacy by design and a Data Protection Impact Assessment where required.
- Academic results and case evidence are confidential. Students see their own records only; lecturers see assigned units; reviewers and offices see cases within delegated scope.
- Use institutional identity/SSO when available, MFA for privileged roles, least privilege, secure sessions, audit logging, encrypted backups and key rotation.
- Never store real student data or private keys in source control, test fixtures, browser storage or public blockchains.
- Keep staff-only investigation notes separate from student-visible case updates.
- Define retention and archival schedules with the university; do not keep everything forever merely because blockchain is immutable.
- Build correction and appeal workflows. Immutable audit evidence does not mean an incorrect academic record can never be corrected.
- Conduct independent security review and smart-contract audit before production.

## 11. Golden-path implementation sequence

Phase 0 — Discovery and policy validation:
- Interview students, lecturers, invigilators, HODs, school examination coordinators, exam office, Senate/Academic Registrar representatives and ICT.
- Observe one CAT capture and one final-exam workflow end-to-end.
- Obtain approved blank forms/templates: exam card, attendance register, script packet/receipt, marks sheet, missing-mark form, Senate result approval and portal import format.
- Map actual deadlines, roles, exceptions, appeals, publication embargoes and records-retention requirements.
- Validate all Karatina-specific assumptions with authorised staff; public notices alone do not define the full policy.

Phase 1 — Reliable digital workflow (LOCAL_ONLY):
- Add assessment-level records for CAT 1/2/3 and final exam separately.
- Add registration/eligibility snapshots, attendance entries, script custody and marking status.
- Add complete-batch validation and reason-coded missing outcomes.
- Add durable submission receipts, case ownership, deadlines, escalation and student tracking.
- Add role-separated review, exam-office processing, Senate gate and portal import receipt.
- Preserve existing data and current working features through migrations and regression tests.

Phase 2 — Reconciliation and operational intelligence:
- Build deterministic rules-based reconciliation before AI.
- Add dashboards for missing evidence, overdue stages, batch omissions and portal mismatches.
- Add AI case summaries and anomaly suggestions with evidence citations and human approval.
- Measure false positives and missed detections before expanding AI.

Phase 3 — Independent audit:
- Strengthen commitment scheme and transaction idempotency.
- Anchor batch revisions and approval-event commitments.
- Reconcile database state, stored snapshots and chain state.
- Test outages, delayed confirmations, reverted transactions, key compromise and recovery.

Phase 4 — Controlled pilot:
- Synthetic data first; then a small authorised pilot with institutional approval.
- Pilot one department and a limited set of units across CAT and final examination.
- Run in parallel with official systems; MarkTrail must not become the official source of marks until formally approved.
- Review every discrepancy and collect student/staff feedback.
- Expand only after measurable success and security/privacy sign-off.

## 12. Acceptance criteria

A release is not complete until automated tests demonstrate:
- Every enrolled candidate has an explicit state for every required assessment component.
- A batch with unexplained omissions cannot be submitted.
- Attendance signature absence creates a reviewable exception, not an automatic zero.
- A signed attendance entry without a script receipt remains distinguishable from a collected script.
- A script receipt without a mark is detectable.
- Every handoff has a receiver acknowledgement or an explicit exception.
- CAT publication and final-result publication obey separate configurable approval gates.
- Senate-pending results cannot appear as final/published.
- Portal imports are reconciled against the approved batch.
- Amendments preserve prior values and require reason, actor and required approvals.
- Duplicate submissions and retries are idempotent.
- AI cannot write marks or make final academic decisions.
- Role isolation, privacy boundaries, audit history, backups and recovery are tested.
- LOCAL_ONLY and chain-anchored states are never confused.
- All critical scenarios in the persona tabletop have regression tests.

## 13. Measures of success

Measure the process, not blockchain activity:
- Percentage of assessment components with complete evidence before result publication.
- Number of missing-mark cases per 1,000 candidate-assessment records.
- Median and 90th-percentile time to resolve a case.
- Percentage of cases automatically localised to a failed workflow stage.
- Number of scripts with custody gaps.
- Number of batches rejected for omissions or identity mismatches before submission.
- Percentage of final results whose portal import matches the Senate-approved batch.
- Number of silent amendments (target: zero).
- AI false-positive and false-negative rates.
- Student effort: number of offices/visits/messages needed to resolve one case.

## 14. Non-negotiable principles

1. No fabricated marks.
2. No silent edits or deletions.
3. No automatic zero from a missing signature alone.
4. No AI-only academic decisions.
5. No personal student data or marks on a public blockchain.
6. No claim of official publication before the proper approval gate and portal reconciliation.
7. No blaming a person based only on an anomaly.
8. Every case has an owner, next action and escalation route.
9. Preserve old evidence when correcting a record.
10. The institution's approved academic regulations remain authoritative.
