// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
contract BountyArena is Ownable {
    constructor() Ownable(msg.sender) {}
    error noway();
    enum status {
        open,
        claimed,
        submitted,
        completed
    }
    struct Bounty {
        address creator;
        address hunter;
        uint256 amount;
        string description;
        bytes32 solutionHash;
        status currentstatus;
        //bytes32[]tags;
    }
    //bytes32[] tags;
    //bytes32 ID=keccak256(abi.encodePacked(msg.sender,block.timestamp));
    mapping(bytes32 ID => Bounty) public bounties;

    function createbounty(
        address addr,
        uint256 amount
        //string memory description
    ) external payable returns (bytes32) {
        require(amount >= 0, "topup");
        require(amount == msg.value, "attach eth");

        bytes32 ID = keccak256(abi.encode(msg.sender, block.timestamp));

        bounties[ID] = Bounty({
            creator: msg.sender,
            hunter: addr,
            amount: amount,
            description: "this bounty is",
            solutionHash: bytes32("usr1"),
            currentstatus: status.open
          //  tags: [bytes32("solidity")]
        });
        //tags: bytes32["solidity"]
        require(amount >= 0, "topup");
        require(amount == msg.value, "attach eth");

        return (ID);
    }

    function claimbounty() external {
        //if( msg.sender!= bounties[ID].hunter){revert noway();}
    }
}
