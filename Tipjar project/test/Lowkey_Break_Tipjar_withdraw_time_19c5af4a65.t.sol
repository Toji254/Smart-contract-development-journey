// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakTime is Test {
    address constant TARGET = address(0x5fbdb2315678afecb367f032d93f642f64180aa3);
    address constant ATTACKER = address(0xBEEF000000000000000000000000000000000042);

    function test_time_dependence() public {
        bytes memory data = hex"fef3a300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
        vm.deal(ATTACKER, 100 ether);

        vm.warp(100000);
        vm.prank(ATTACKER);
        (bool first, bytes memory a) = TARGET.call{value: 0}(data);

        vm.warp(200000);
        vm.prank(ATTACKER);
        (bool second, bytes memory b) = TARGET.call{value: 0}(data);

        console2.log("LOWKEY_BREAK_FAMILY", "time");
        console2.log("FIRST_SUCCESS", first);
        console2.log("SECOND_SUCCESS", second);
        console2.log("RETURN_DATA_CHANGED", keccak256(a) != keccak256(b));
        console2.log("LOWKEY_BREAK", false);
    }
}
