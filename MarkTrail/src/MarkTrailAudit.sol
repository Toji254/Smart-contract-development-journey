// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MarkTrailAudit
/// @notice On-chain audit layer for academic mark batches.
/// @dev Actual marks remain off-chain. The contract stores commitments and revision history.
contract MarkTrailAudit {
    enum BatchStatus {
        NONE,
        SUBMITTED,
        VERIFIED,
        AMENDED
    }

    struct Revision {
        bytes32 marksHash;
        bytes32 reasonHash;
        address actor;
        uint64 timestamp;
    }

    struct Batch {
        bytes32 courseId;
        bytes32 assessmentId;
        uint32 studentCount;
        BatchStatus status;
        uint64 submittedAt;
        uint256 revisionCount;
    }

    address public owner;

    mapping(address => bool) public lecturers;
    mapping(address => bool) public reviewers;
    mapping(bytes32 => Batch) private batches;
    mapping(bytes32 => Revision[]) private revisions;

    error NotOwner();
    error NotLecturer();
    error NotReviewer();
    error ZeroAddress();
    error EmptyIdentifier();
    error EmptyHash();
    error EmptyReason();
    error BatchAlreadyExists();
    error BatchNotFound();
    error InvalidStatus();

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event LecturerUpdated(address indexed account, bool enabled);
    event ReviewerUpdated(address indexed account, bool enabled);

    event BatchSubmitted(
        bytes32 indexed batchId,
        bytes32 indexed courseId,
        bytes32 indexed assessmentId,
        bytes32 marksHash,
        uint32 studentCount,
        address submittedBy
    );

    event BatchVerified(bytes32 indexed batchId, address indexed reviewer);

    event BatchAmended(
        bytes32 indexed batchId,
        bytes32 marksHash,
        bytes32 reasonHash,
        address amendedBy,
        uint256 revision
    );

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyLecturer() {
        if (!lecturers[msg.sender]) revert NotLecturer();
        _;
    }

    modifier onlyReviewer() {
        if (!reviewers[msg.sender]) revert NotReviewer();
        _;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
    }

    function setLecturer(address account, bool enabled) external onlyOwner {
        if (account == address(0)) revert ZeroAddress();

        lecturers[account] = enabled;
        emit LecturerUpdated(account, enabled);
    }

    function setReviewer(address account, bool enabled) external onlyOwner {
        if (account == address(0)) revert ZeroAddress();

        reviewers[account] = enabled;
        emit ReviewerUpdated(account, enabled);
    }

    /// @notice Register the first commitment for a marks batch.
    /// @dev The application should hash a canonical, salted representation off-chain.
    function submitBatch(
        bytes32 batchId,
        bytes32 courseId,
        bytes32 assessmentId,
        uint32 studentCount,
        bytes32 marksHash
    ) external onlyLecturer {
        if (
            batchId == bytes32(0) ||
            courseId == bytes32(0) ||
            assessmentId == bytes32(0)
        ) {
            revert EmptyIdentifier();
        }

        if (marksHash == bytes32(0)) revert EmptyHash();
        if (batches[batchId].status != BatchStatus.NONE) {
            revert BatchAlreadyExists();
        }

        batches[batchId] = Batch({
            courseId: courseId,
            assessmentId: assessmentId,
            studentCount: studentCount,
            status: BatchStatus.SUBMITTED,
            submittedAt: uint64(block.timestamp),
            revisionCount: 1
        });

        revisions[batchId].push(
            Revision({
                marksHash: marksHash,
                reasonHash: bytes32(0),
                actor: msg.sender,
                timestamp: uint64(block.timestamp)
            })
        );

        emit BatchSubmitted(
            batchId,
            courseId,
            assessmentId,
            marksHash,
            studentCount,
            msg.sender
        );
    }

    /// @notice Verify the current batch revision and make it eligible for publication.
    function verifyBatch(bytes32 batchId) external onlyReviewer {
        Batch storage batch = batches[batchId];

        if (batch.status == BatchStatus.NONE) revert BatchNotFound();

        if (
            batch.status != BatchStatus.SUBMITTED &&
            batch.status != BatchStatus.AMENDED
        ) {
            revert InvalidStatus();
        }

        batch.status = BatchStatus.VERIFIED;

        emit BatchVerified(batchId, msg.sender);
    }

    /// @notice Record a new commitment after a verified batch is changed.
    /// @dev The previous commitment remains queryable through getRevision.
    function amendBatch(
        bytes32 batchId,
        bytes32 newMarksHash,
        bytes32 reasonHash
    ) external onlyLecturer {
        Batch storage batch = batches[batchId];

        if (batch.status == BatchStatus.NONE) revert BatchNotFound();
        if (batch.status != BatchStatus.VERIFIED) revert InvalidStatus();
        if (newMarksHash == bytes32(0)) revert EmptyHash();
        if (reasonHash == bytes32(0)) revert EmptyReason();

        batch.status = BatchStatus.AMENDED;
        batch.revisionCount += 1;

        revisions[batchId].push(
            Revision({
                marksHash: newMarksHash,
                reasonHash: reasonHash,
                actor: msg.sender,
                timestamp: uint64(block.timestamp)
            })
        );

        emit BatchAmended(
            batchId,
            newMarksHash,
            reasonHash,
            msg.sender,
            batch.revisionCount
        );
    }

    function getBatch(
        bytes32 batchId
    )
        external
        view
        returns (
            bytes32 courseId,
            bytes32 assessmentId,
            uint32 studentCount,
            BatchStatus status,
            uint64 submittedAt,
            uint256 revisionCount
        )
    {
        Batch memory batch = batches[batchId];

        if (batch.status == BatchStatus.NONE) revert BatchNotFound();

        return (
            batch.courseId,
            batch.assessmentId,
            batch.studentCount,
            batch.status,
            batch.submittedAt,
            batch.revisionCount
        );
    }

    function getRevisionCount(bytes32 batchId) external view returns (uint256) {
        if (batches[batchId].status == BatchStatus.NONE) revert BatchNotFound();
        return revisions[batchId].length;
    }

    function getRevision(
        bytes32 batchId,
        uint256 index
    )
        external
        view
        returns (
            bytes32 marksHash,
            bytes32 reasonHash,
            address actor,
            uint64 timestamp
        )
    {
        if (batches[batchId].status == BatchStatus.NONE) revert BatchNotFound();

        Revision memory revision = revisions[batchId][index];

        return (
            revision.marksHash,
            revision.reasonHash,
            revision.actor,
            revision.timestamp
        );
    }

    function getCurrentRevision(
        bytes32 batchId
    )
        external
        view
        returns (
            bytes32 marksHash,
            bytes32 reasonHash,
            address actor,
            uint64 timestamp
        )
    {
        if (batches[batchId].status == BatchStatus.NONE) revert BatchNotFound();

        Revision memory revision = revisions[batchId][revisions[batchId].length - 1];

        return (
            revision.marksHash,
            revision.reasonHash,
            revision.actor,
            revision.timestamp
        );
    }
}
