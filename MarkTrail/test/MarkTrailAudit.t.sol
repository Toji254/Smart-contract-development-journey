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
            ,
            uint256 revisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(courseId == COURSE_ID);
        assert(assessmentId == ASSESSMENT_ID);
        assert(studentCount == 87);
        assert(status == MarkTrailAudit.BatchStatus.SUBMITTED);
        assert(revisionCount == 1);
        assert(audit.getRevisionCount(BATCH_ID) == 1);

        (
            bytes32 storedHash,
            bytes32 reasonHash,
            address actor,
        ) = audit.getRevision(BATCH_ID, 0);

        assert(storedHash == HASH_V1);
        assert(reasonHash == bytes32(0));
        assert(actor == address(this));
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
            ,
            ,
            ,
            MarkTrailAudit.BatchStatus verifiedStatus,
            ,
            uint256 verifiedRevisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(verifiedStatus == MarkTrailAudit.BatchStatus.VERIFIED);
        assert(verifiedRevisionCount == 1);

        audit.amendBatch(BATCH_ID, HASH_V2, REASON);

        (
            ,
            ,
            ,
            MarkTrailAudit.BatchStatus amendedStatus,
            ,
            uint256 amendedRevisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(amendedStatus == MarkTrailAudit.BatchStatus.AMENDED);
        assert(amendedRevisionCount == 2);
        assert(audit.getRevisionCount(BATCH_ID) == 2);

        (bytes32 oldHash, , , ) = audit.getRevision(BATCH_ID, 0);
        (bytes32 newHash, bytes32 reasonHash, , ) = audit.getRevision(BATCH_ID, 1);

        assert(oldHash == HASH_V1);
        assert(newHash == HASH_V2);
        assert(reasonHash == REASON);
    }

    function testAmendmentMustFollowVerification() public {
        audit.submitBatch(
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );

        UnauthorizedCaller attacker = new UnauthorizedCaller();
        bool succeeded = attacker.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V2
        );

        assert(!succeeded);
    }
}
