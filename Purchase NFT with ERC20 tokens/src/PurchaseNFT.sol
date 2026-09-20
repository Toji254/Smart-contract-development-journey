//SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {
    ERC721URIStorage,
    ERC721
} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";

contract PurchaseNFT is ERC721URIStorage {
    address public immutable OWNER;
    uint256 public createnewtoken = 0;

    constructor() ERC721("LOKI254", "LOKI") {
        OWNER = msg.sender;
    }

    function mint(address user) public returns (uint256) {
        _safeMint(user, createnewtoken);

        createnewtoken++;
        return createnewtoken;
    }
}
