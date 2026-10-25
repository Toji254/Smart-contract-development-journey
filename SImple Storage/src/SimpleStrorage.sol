// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract SimpleStorage{

uint256 public value;

constructor(uint256 _value){
    value=_value;
}

//mapping (address => uint256 number) private _value;

function setvalue(uint256 _value)external{
    value = _value;

}

function increase(uint256 add)external {
    value+=add;
}

function decrease(uint256 minus)external {
    value-=minus;
}

}
