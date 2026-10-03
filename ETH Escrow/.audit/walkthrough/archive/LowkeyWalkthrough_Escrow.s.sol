// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

contract LowkeyWalkthrough_Escrow is Script {
    // Generated from successful observations captured by Lowkey on local Anvil.
    // The script replays the exact transaction calldata whenever available.
    function run() external {
        vm.startBroadcast(vm.envUint("LOWKEY_LAB_DEPLOYER_KEY"));
        address target_1 = address(uint160(0xe7f1725e7734ce288f8367e1bb143e90bb3f0512));
        (bool ok_1, ) = target_1.call{value: 0}(hex"294861d50000000000000000000000000000000000000000000000000de0b6b3a764000000000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c8");
        require(ok_1, "walkthrough replay step reverted");
        address target_2 = address(uint160(0xe7f1725e7734ce288f8367e1bb143e90bb3f0512));
        (bool ok_2, ) = target_2.call{value: 0}(hex"86d1a69f");
        require(ok_2, "walkthrough replay step reverted");
        vm.stopBroadcast();
    }
}
