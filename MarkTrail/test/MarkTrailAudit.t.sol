// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {MarkTrailAudit} from "../src/MarkTrailAudit.sol";

contract RoleActor {
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

    function verify(MarkTrailAudit target, bytes32 batchId) external returns (bool) {
        try target.verifyBatch(batchId) {
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

    function transfer(
        MarkTrailAudit target,
        address newOwner
    ) external returns (bool) {
        try target.transferOwnership(newOwner) {
            return true;
        } catch {
            return false;
        }
    }
}

contract MarkTrailAuditTest {
    MarkTrailAudit internal audit;
    RoleActor internal lecturer;
    RoleActor internal reviewer;
    RoleActor internal attacker;

    bytes32 internal constant BATCH_ID = keccak256("CSC201-CAT2-2026");
    bytes32 internal constant COURSE_ID = keccak256("CSC201");
    bytes32 internal constant ASSESSMENT_ID = keccak256("CAT2");
    bytes32 internal constant HASH_V1 = keccak256("salted-batch-v1");
    bytes32 internal constant HASH_V2 = keccak256("salted-batch-v2");
    bytes32 internal constant REASON = keccak256("marking-correction");

    function setUp() public {
        audit = new MarkTrailAudit();
        lecturer = new RoleActor();
        reviewer = new RoleActor();
        attacker = new RoleActor();

        audit.setLecturer(address(lecturer), true);
        audit.setReviewer(address(reviewer), true);
    }

    function _submit() internal {
        bool succeeded = lecturer.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );
        assert(succeeded);
    }

    function _verify() internal {
        bool succeeded = reviewer.verify(audit, BATCH_ID);
        assert(succeeded);
    }

    function testInitialSubmissionStoresAuditRecord() public {
        _submit();

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
            uint64 timestamp
        ) = audit.getCurrentRevision(BATCH_ID);

        assert(storedHash == HASH_V1);
        assert(reasonHash == bytes32(0));
        assert(actor == address(lecturer));
        assert(timestamp > 0);
    }

    function testUnauthorizedAccountsCannotSubmitOrVerify() public {
        bool submitSucceeded = attacker.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V1
        );
        assert(!submitSucceeded);

        bool verifySucceeded = attacker.verify(audit, BATCH_ID);
        assert(!verifySucceeded);
    }

    function testDuplicateBatchFails() public {
        _submit();

        bool succeeded = lecturer.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            HASH_V2
        );

        assert(!succeeded);
    }

    function testVerificationPublishesCurrentRevision() public {
        _submit();
        _verify();

        (
            ,
            ,
            ,
            MarkTrailAudit.BatchStatus status,
            ,
            uint256 revisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(status == MarkTrailAudit.BatchStatus.VERIFIED);
        assert(revisionCount == 1);
    }

    function testAmendmentRequiresVerificationAndPreservesHistory() public {
        _submit();

        bool tooEarly = lecturer.amend(
            audit,
            BATCH_ID,
            HASH_V2,
            REASON
        );
        assert(!tooEarly);

        _verify();

        bool amended = lecturer.amend(
            audit,
            BATCH_ID,
            HASH_V2,
            REASON
        );
        assert(amended);

        (
            ,
            ,
            ,
            MarkTrailAudit.BatchStatus status,
            ,
            uint256 revisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(status == MarkTrailAudit.BatchStatus.AMENDED);
        assert(revisionCount == 2);
        assert(audit.getRevisionCount(BATCH_ID) == 2);

        (bytes32 oldHash, , , ) = audit.getRevision(BATCH_ID, 0);
        (bytes32 newHash, bytes32 reasonHash, address actor, ) =
            audit.getRevision(BATCH_ID, 1);

        assert(oldHash == HASH_V1);
        assert(newHash == HASH_V2);
        assert(reasonHash == REASON);
        assert(actor == address(lecturer));
    }

    function testInvalidInputFails() public {
        bool zeroHash = lecturer.submit(
            audit,
            BATCH_ID,
            COURSE_ID,
            ASSESSMENT_ID,
            87,
            bytes32(0)
        );
        assert(!zeroHash);

        bool zeroCourse = lecturer.submit(
            audit,
            BATCH_ID,
            bytes32(0),
            ASSESSMENT_ID,
            87,
            HASH_V1
        );
        assert(!zeroCourse);
    }

    function testOwnershipCanBeTransferredOnlyByOwner() public {
        bool attackerTransfer = attacker.transfer(audit, address(attacker));
        assert(!attackerTransfer);

        audit.transferOwnership(address(attacker));
        assert(audit.owner() == address(attacker));

        bool originalOwnerRoleUpdate = false;
        try audit.setLecturer(address(lecturer), false) {
            originalOwnerRoleUpdate = true;
        } catch {}

        assert(!originalOwnerRoleUpdate);
    }

    function testReviewerCanVerifyAfterAmendment() public {
        _submit();
        _verify();
        assert(lecturer.amend(audit, BATCH_ID, HASH_V2, REASON));

        assert(reviewer.verify(audit, BATCH_ID));

        (
            ,
            ,
            ,
            MarkTrailAudit.BatchStatus status,
            ,
            uint256 revisionCount
        ) = audit.getBatch(BATCH_ID);

        assert(status == MarkTrailAudit.BatchStatus.VERIFIED);
        assert(revisionCount == 2);
    }
}
