
// LOWKEY AUDIT CONTEXT
// Signal       : none selected
// Issue        : no focused signal
// Detector     : manual/none
// Mode         : generic
// Impact       : unknown
// Confidence   : unknown
// Location     : unknown:?
// Function     : not resolved
// Description  : none
// Slither      : 3 finding(s)
// Source scan  : not recorded review marker(s)
// Risk map     : not recorded function row(s)
// Trace        : not recorded
// Latest tx    : 0xad8fe3804c488a3a4c7995f638cf56ccbc678dc2e1021994f7228ba9f69cb073
// Open signals : 0
// NOTE: this context is evidence for investigation, not proof that the detector is exploitable.
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {Vm} from "forge-std/Vm.sol";

/// @title Lowkey-generated proof of concept
/// @notice Replays one concrete call and exposes the measurements needed for a security property.
contract LowkeyPoC_Escrow is Script {
    address internal constant TARGET = address(uint160(0x008a791620dd6260079bf849dc5567adc3f2fdc318));

    function run() external {
        // SAFETY: start with Anvil or a local fork. A broadcasted script changes real chain state.
        // The private key stays outside source code and is loaded from the environment here.
        uint256 attackerKey = vm.envUint("LOWKEY_ATTACKER_KEY");
        address attacker = vm.addr(attackerKey);

        vm.startBroadcast(attackerKey);

        // recordLogs captures emitted events so you can inspect behavior, not just balances.
        vm.recordLogs();
        vm.record();

        uint256 attackerBefore = attacker.balance;
        uint256 targetBefore = TARGET.balance;

        // Raw call is intentional: it replays exact calldata while you are still learning the ABI.
        // Later, replace this with a typed interface call once the contract behavior is understood.
        // forge-lint: disable-next-line low-level-calls
        (bool success, bytes memory returndata) =
            TARGET.call{value: 0 wei}(hex"294861d50000000000000000000000000000000000000000000000000de0b6b3a764000000000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c8");

        uint256 attackerAfter = attacker.balance;

        // accesses exposes storage slots this transaction read/wrote.
        // This is the Solidity-side counterpart to Lowkey's transaction state-diff workflow.
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(TARGET);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        uint256 targetAfter = TARGET.balance;

        vm.stopBroadcast();

        console2.log("Function:", "createescrow(uint256,address)");
        console2.log("Success:", success);
        console2.log("Target before:", targetBefore);
        console2.log("Target after:", targetAfter);
        console2.log("Attacker before:", attackerBefore);
        console2.log("Attacker after:", attackerAfter);
        console2.log("Storage reads:", reads.length);
        console2.log("Storage writes:", writes.length);
        console2.log("Events emitted:", logs.length);
        console2.logBytes(returndata);

        // Raw write-slot addresses are useful first evidence. Decode mapping/struct slots after that.
        for (uint256 i = 0; i < writes.length; i++) {
            console2.logBytes32(writes[i]);
        }

        // A successful call only means it did not revert. It is NOT proof of a vulnerability.
        require(success, "Lowkey PoC: target call reverted");

        // Put the actual security property here:
        // require(attackerAfter > attackerBefore, "exploit condition not met");
        // require(TARGET.balance < targetBefore, "expected loss did not occur");
    }
}
