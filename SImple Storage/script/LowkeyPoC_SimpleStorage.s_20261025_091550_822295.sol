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
// Security     : none [none]
// Slither      : not recorded finding(s)
// Source scan  : not recorded review marker(s)
// Risk map     : not recorded function row(s)
// Trace        : not recorded
// Latest tx    : 0xbf2cd105fb4be4e6b5e18447aa91fcab7d4ac7090ba5d87d676295421a845680
// Open signals : 1
// NOTE: this context is evidence for investigation, not proof that the detector is exploitable.
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {Vm} from "forge-std/Vm.sol";

interface IERC20Lowkey {
    function balanceOf(address account) external view returns (uint256);
}

contract LowkeyPoC_SimpleStorage is Script {
    address internal constant TARGET = address(uint160(0x00e7f1725E7734CE288F8367e1Bb143E90bb3F0512));

    struct TokenSnapshot {
        address token;
        bool tracked;
        uint256 targetBalance;
        uint256 attackerBalance;
    }

    function _tokenSnapshot(address attacker) internal view returns (TokenSnapshot memory snapshot) {
        (bool ok, bytes memory data) = TARGET.staticcall(abi.encodeWithSignature("stakeToken()"));
        if (!ok || data.length < 32) {
            (ok, data) = TARGET.staticcall(abi.encodeWithSignature("asset()"));
        }
        if (ok && data.length >= 32) {
            address token = abi.decode(data, (address));
            if (token != address(0) && token.code.length > 0) {
                snapshot.token = token;
                snapshot.tracked = true;
                snapshot.targetBalance = IERC20Lowkey(token).balanceOf(TARGET);
                snapshot.attackerBalance = IERC20Lowkey(token).balanceOf(attacker);
            }
        }
    }

    function _tokenAfter(TokenSnapshot memory beforeSnapshot, address attacker)
        internal
        view
        returns (TokenSnapshot memory afterSnapshot)
    {
        afterSnapshot = beforeSnapshot;
        if (beforeSnapshot.tracked) {
            afterSnapshot.targetBalance = IERC20Lowkey(beforeSnapshot.token).balanceOf(TARGET);
            afterSnapshot.attackerBalance = IERC20Lowkey(beforeSnapshot.token).balanceOf(attacker);
        }
    }

    function _logEvidence(
        bool success,
        bytes memory returndata,
        uint256 targetBefore,
        uint256 targetAfter,
        uint256 attackerBefore,
        uint256 attackerAfter,
        TokenSnapshot memory tokenBefore,
        TokenSnapshot memory tokenAfter
    ) internal {
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(TARGET);
        Vm.Log[] memory logs = vm.getRecordedLogs();

        console2.log("Function:", "increase(uint256)");
        console2.log("Success:", success);
        console2.log("Target before:", targetBefore);
        console2.log("Target after:", targetAfter);
        console2.log("Attacker before:", attackerBefore);
        console2.log("Attacker after:", attackerAfter);
        console2.log("Storage reads:", reads.length);
        console2.log("Storage writes:", writes.length);
        console2.log("Events emitted:", logs.length);
        console2.log("Asset token tracked:", tokenBefore.tracked);
        console2.log("Target token before:", tokenBefore.targetBalance);
        console2.log("Target token after:", tokenAfter.targetBalance);
        console2.log("Attacker token before:", tokenBefore.attackerBalance);
        console2.log("Attacker token after:", tokenAfter.attackerBalance);
        console2.logBytes(returndata);

        for (uint256 i = 0; i < writes.length; i++) {
            console2.logBytes32(writes[i]);
        }
    }

    function run() external {
        address attacker;

        vm.startBroadcast();
        (, attacker,) = vm.readCallers();

        vm.recordLogs();
        vm.record();

        uint256 attackerBefore = attacker.balance;
        uint256 targetBefore = TARGET.balance;
        TokenSnapshot memory tokenBefore = _tokenSnapshot(attacker);

        // Raw call is intentional: it replays exact calldata while you are still learning the ABI.
        // Later, replace this with a typed interface call once the contract behavior is understood.
        // forge-lint: disable-next-line(low-level-calls)
        (bool success, bytes memory returndata) =
            TARGET.call{value: 0 wei}(hex"30f3f0db0000000000000000000000000000000000000000000000000000000000000001");

        uint256 attackerAfter = attacker.balance;
        uint256 targetAfter = TARGET.balance;
        TokenSnapshot memory tokenAfter = _tokenAfter(tokenBefore, attacker);

        vm.stopBroadcast();

        _logEvidence(
            success, returndata, targetBefore, targetAfter, attackerBefore, attackerAfter, tokenBefore, tokenAfter
        );

        // A successful call only means it did not revert. It is NOT proof of a vulnerability.
        require(success, "Lowkey PoC: target call reverted");

        // Put the actual security property here:
        // require(attackerAfter > attackerBefore, "exploit condition not met");
        // require(TARGET.balance < targetBefore, "expected loss did not occur");
    }
}
