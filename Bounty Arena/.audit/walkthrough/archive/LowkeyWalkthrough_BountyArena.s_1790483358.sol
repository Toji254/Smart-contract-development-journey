// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

contract LowkeyWalkthrough_BountyArena is Script {
    // Generated from successful observations captured by Lowkey on local Anvil.
    // The script replays the exact transaction calldata whenever available.
    function run() external {
        vm.startBroadcast(vm.envUint("LOWKEY_ALICE_KEY"));
        address target_1 = address(uint160(0x0165878A594ca255338adfa4d48449f69242Eb8F));
        (bool ok_1, ) = target_1.call{value: 1000000000000000000}(hex"c455ed75000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb922660000000000000000000000000000000000000000000000000de0b6b3a7640000");
        require(ok_1, "walkthrough replay step reverted");
        vm.stopBroadcast();
    }
}
