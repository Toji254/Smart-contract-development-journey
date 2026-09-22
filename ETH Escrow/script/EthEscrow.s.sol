//SPDX Licence-Identifier:MIT

pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/EthEscrow.sol";

contract deployEthEscrow is Script {
    function run() external returns (Escrow) {
        vm.startBroadcast();

        Escrow escrow = new Escrow();

        vm.stopBroadcast();
    }
}
