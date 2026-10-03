// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {Vm} from "forge-std/Vm.sol";
import { Escrow } from "../src/EthEscrow.sol";

/// @title Lowkey-generated deployment for Escrow
/// @notice Reusable Foundry deployment plus post-deployment audit hooks.
contract LowkeyDeploy_Escrow is Script {
    string internal constant DEPLOYMENT_DIR = "deployments";

    function run() external returns (Escrow instance) {
        // Keep private keys in Forge CLI flags or environment variables, never in this source file.
        // startBroadcast tells Foundry that the following deployment transaction is the one to broadcast.
        vm.startBroadcast();

        instance = new Escrow();

        vm.stopBroadcast();

        _postDeployChecks(instance);
        _writeDeploymentRecord(instance);
        return instance;
    }

    function _postDeployChecks(Escrow instance) internal view {
        // Confirms deployment left runtime bytecode at the returned address.
        // This is a deployment sanity check, not a security proof.
        require(address(instance).code.length > 0, "Lowkey: no runtime bytecode");
        console2.log("Deployed:", address(instance));
        console2.log("Chain ID:", block.chainid);
        console2.log("Code bytes:", address(instance).code.length);
    }

    function _writeDeploymentRecord(Escrow instance) internal {
        // serialize* + writeJson creates machine-readable evidence for later scripts and audits.
        string memory json = vm.serializeAddress("lowkey", "address", address(instance));
        json = vm.serializeUint("lowkey", "chainId", block.chainid);
        json = vm.serializeString("lowkey", "contract", "Escrow");
        json = vm.serializeString("lowkey", "generatedAt", "2026-09-23T16:28:28");
        vm.writeJson(
            json,
            string.concat(DEPLOYMENT_DIR, "/Escrow-", vm.toString(block.chainid), ".json")
        );
    }
}
