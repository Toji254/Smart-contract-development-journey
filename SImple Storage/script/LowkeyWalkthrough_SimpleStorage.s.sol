// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

contract LowkeyWalkthrough_SimpleStorage is Script {
    // Generated from successful observations captured by Lowkey on local Anvil.
    // The script replays the exact transaction calldata whenever available.
    function run() external {
        vm.startBroadcast(vm.envUint("LOWKEY_ALICE_KEY"));
        address target_1 = address(uint160(1324161310598743833836268493538283093091898295570));
        (bool ok_1, ) = target_1.call{value: 0}(hex"2d6d30620000000000000000000000000000000000000000000000000000000000000001");
        require(ok_1, "walkthrough replay step reverted");
        address target_2 = address(uint160(1324161310598743833836268493538283093091898295570));
        (bool ok_2, ) = target_2.call{value: 0}(hex"30f3f0db0000000000000000000000000000000000000000000000000000000000000001");
        require(ok_2, "walkthrough replay step reverted");
        vm.stopBroadcast();
    }
}
