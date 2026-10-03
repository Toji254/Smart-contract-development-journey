// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
contract Tipjar is Ownable(msg.sender) {
    //constructor()
    error transferfailed();
    event Deposit(uint256);
    mapping(address tipper => uint256 amount) public balances;
    function deposit(/*uint256 amount*/) public payable {
        balances[msg.sender] += msg.value;
        emit Deposit(msg.value);
    }

    function withdraw(address to, uint256 amount) external onlyOwner {
        //require(amount >= 0, "put amount");
        balances[msg.sender] -= amount;
        (bool success, ) = payable(to).call{value: amount}("");
        if (!success) {
            revert transferfailed();
        }
    }
}
