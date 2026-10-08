// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {MarkTrailAudit} from "../src/MarkTrailAudit.sol";

contract UnauthorizedCaller {
    function submit(
        MarkTrailAudit target,
        bytes32 batchId,
        bytes32 courseId,
        bytes32 assessmentId,
        uint32 studentCount,
        bytes32 marksHash
    ) external returns (bool) {
        try
            target.submitBatch(
                batchId,
                courseId,
                assessmentId,
                studentCount,
                marksHash
            )
        {
            return true;
        } catch {
            return false;
        }
    }

    function amend(
        MarkTrailAudit target,
        bytes32 batchId,
        bytes32 newMarksHash,
        bytes32 reasonHash
    ) external returns (bool) {
        try target.amendBatch(batchId, newMarksHash, reasonHash) {
            return true;
        } catch {
            return false;
        }
    }
}

contract MarkTrailAuditTest {
    MarkTrailAudit internal audit;

    bytes32 internal constant BATCH_ID = keccak256("CSC201-CAT2-2026");
    bytes32 internal constant COURSE_ID = keccak256("CSC201");
    bytes32 internal constant ASSESSMENT_ID = keccak256("CAT2");
    bytes32 internal constant HASH_V1 = keccak256("salted-batch-v1");
    bytes32 internal constant HASH_V2 = keccak256("salted-batch-v2");
    bytes32 internal constant REASON = keccak256("marking-correction");

    function setUp() public {
        audit = new MarkTrailAudit();

        audit.setLecturer(address(this), true);
        audit.setReviewer(address(this), true);
    }

    function testSubmitCreatesRevision() public {
        audit.submitBatch(
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );

        (
            bytes32 courseId,
            bytes32 assessmentId,
            uint32 studentCount,
            MarkTrailAudit.BatchStatus status,
            uint64 submittedAt,
            uint256 revisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(courseId == COURSE_ID);
        assert(assessmentId == ASSESSMENT_ID);
        assert(studentCount == 87);
        assert(status == MarkTrailAudit.BatchStatus.SUBMITTED);
        assert(submittedAt > 0);
        assert(revisionCount == 1);
        assert(audit.getRevisionCount(BATCH_ID) == 1);

        (
            bytes32 storedHash,
            bytes32 reasonHash,
            address actor,
            uint64 revisionTimestamp
        ) = audit.getRevision(BATCH_ID, 0);

        assert(storedHash == HASH_V1);
        assert(reasonHash == bytes32(0));
        assert(actor == address(this));
        assert(revisionTimestamp > 0);
    }

    function testOnlyAuthorizedLecturerCanSubmit() public {
        UnauthorizedCaller attacker = new UnauthorizedCaller();

        bool succeeded = attacker.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );

        assert(!succeeded);
        assert(!audit.lecturers(address(attacker)));
    }

    function testVerificationAndAmendmentPreserveHistory() public {
        audit.submitBatch(
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );

        audit.verifyBatch(BATCH_ID);

        (
            bytes32 courseId,
            bytes32 assessmentId,
            uint32 studentCount,
            MarkTrailAudit.BatchStatus verifiedStatus,
            uint64 submittedAt,
            uint256 verifiedRevisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(courseId == COURSE_ID);
        assert(assessmentId == ASSESSMENT_ID);
        assert(studentCount == 87);
        assert(submittedAt > 0);
        assert(verifiedStatus == MarkTrailAudit.BatchStatus.VERIFIED);
        assert(verifiedRevisionCount == 1);

        audit.amendBatch(BATCH_ID, HASH_V2, REASON);

        (
            bytes32 amendedCourseId,
            bytes32 amendedAssessmentId,
            uint32 amendedStudentCount,
            MarkTrailAudit.BatchStatus amendedStatus,
            uint64 amendedSubmittedAt,
            uint256 amendedRevisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(amendedCourseId == COURSE_ID);
        assert(amendedAssessmentId == ASSESSMENT_ID);
        assert(amendedStudentCount == 87);
        assert(amendedSubmittedAt > 0);
        assert(amendedStatus == MarkTrailAudit.BatchStatus.AMENDED);
        assert(amendedRevisionCount == 2);
        assert(audit.getRevisionCount(BATCH_ID) == 2);

        (
            bytes32 oldHash,
            bytes32 oldReasonHash,
            address oldActor,
            uint64 oldTimestamp
        ) = audit.getRevision(BATCH_ID, 0);

        (
            bytes32 newHash,
            bytes32 reasonHash,
            address newActor,
            uint64 newTimestamp
        ) = audit.getRevision(BATCH_ID, 1);

        assert(oldHash == HASH_V1);
        assert(oldReasonHash == bytes32(0));
        assert(oldActor == address(this));
        assert(oldTimestamp > 0);

        assert(newHash == HASH_V2);
        assert(reasonHash == REASON);
        assert(newActor == address(this));
        assert(newTimestamp > 0);
    }

    function testAmendmentMustFollowVerification() public {
        audit.submitBatch(
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );

        try audit.amendBatch(BATCH_ID, HASH_V2, REASON) {
            assert(false);
        } catch {}
    }

    function testUnauthorizedCallerCannotAmend() public {
        audit.submitBatch(
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );
        audit.verifyBatch(BATCH_ID);

        UnauthorizedCaller attacker = new UnauthorizedCaller();

        bool succeeded = attacker.amend(audit, BATCH_ID, HASH_V2, REASON);

        assert(!succeeded);
    }
}
