// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

contract Tipjar {
    address public immutable OWNER;

    constructor() {
        OWNER = msg.sender;
    }

    modifier onlyowner(){
       require(msg.sender == OWNER,"notowner");
        _;
    }

    mapping(address user => uint256 tip) public usertips;

    event Tips(uint256 tip, address user);

    function tiprecepient(uint256 tip) external payable {
        tip = msg.value;

        tip=msg.value++;

        emit Tips(msg.value, msg.sender);
    }

    function onlyowner() withdraw(uint256 tip,address recipient)external{

    }
}
