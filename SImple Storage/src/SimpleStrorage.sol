// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract SimpleStorage{
//uint256 value;
mapping (address => uint256 number) private value;

function checkvalue() external view returns(uint256){
return value[msg.sender];
//value[]
}
}
