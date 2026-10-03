// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";


contract Poc_locked_ether is Test {
    address internal constant TARGET = address(uint160(0x000165878A594ca255338adfa4d48449f69242Eb8F));
    event EvidenceBool(string name, bool value);
    

    // Candidate detector: locked-ether (medium/high)
    // Candidate function: createbounty(address,uint256)
    // Finding summary: Contract locking ether found: 	Contract BountyArena (src/BountyArena.sol#4-46) has payable functions: 	 - BountyArena.createbounty(address,uint256) (src/BountyArena.sol#25-45) 	But does not have a function to withdraw the ether 
    // Evidence records captured: audit_start, build, context, coverage, geiger, lint, poc, session_resume, slither, slither.raw, source_triage, system_bootstrap, tests, walkthrough
    // Prior trace tx: None
    // Prior storage changes: 0
    // Risk rows captured: 0

    

    function test_poc_candidate() external {
        vm.skip(true); // REMOVE after filling the proven exploit path.
        bytes memory payload = hex"";
        // forge-lint: disable-next-line low-level-calls
        (bool ok, bytes memory data) = TARGET.call(payload);
        assertTrue(ok, string(data));
        // NEXT STEP: assert the violated invariant, unauthorized effect, or asset delta.
    }

}
