// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakBoundary is Test {
    address constant TARGET = address(0x5fbdb2315678afecb367f032d93f642f64180aa3);
    address constant ATTACKER = address(0xBEEF000000000000000000000000000000000042);

    function test_break_boundary() public {
        vm.deal(ATTACKER, 100 ether);
        bytes memory zeroData = hex"fef3a300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
        bytes memory maxData = hex"fef3a3000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb92266ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";

        vm.prank(ATTACKER);
        (bool zeroSuccess, ) = TARGET.call{value: 0}(zeroData);

        vm.prank(ATTACKER);
        (bool maxSuccess, ) = TARGET.call{value: 0}(maxData);

        console2.log("LOWKEY_BREAK_FAMILY", "boundary");
        console2.log("ZERO_SUCCESS", zeroSuccess);
        console2.log("MAX_SUCCESS", maxSuccess);

        // A successful edge call is a lead; Lowkey only turns it into BREAK when
        // the call also produces an observable value/state condition outside its
        // normal entitlement.
        console2.log("LOWKEY_BREAK", false);
    }
}
