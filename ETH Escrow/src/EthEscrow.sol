//SPDX Licence-Identifier:MIT

pragma solidity ^0.8.20;

contract Escrow {
    event CreateEscrow(uint256 indexed amount, address indexed creator);

    error transferfailed();

    mapping(address => uint256 amount) public balances;
    mapping(uint256 value => Create Escrow) public escrow;

    enum status {
        waiting,
        funded,
        rejected,
        released
    }

    struct Create {
        address creator;
        address recipient;
        uint256 amount;
        status currentstatus;
    }

    //modifier onlyrecipient(){
    //require(escrow[1].recipient!=msg.sender);
    //_;
    //}
    function createescrow(uint256 amount, address recipient) external payable {
        balances[msg.sender] += msg.value;
        amount += msg.value;
        escrow[1] = Create({
            creator: msg.sender,
            recipient: recipient,
            amount: msg.value,
            currentstatus: status.waiting
        });
        emit CreateEscrow(msg.value, msg.sender);
    }

    function acceptescrow(bool accept) external {
        if (escrow[1].recipient != msg.sender) {
            revert();
        }
        if (!accept) {
            escrow[1].currentstatus = status.rejected;
        }
        require(accept, "rejected");
         if (accept) {
            escrow[1].currentstatus = status.funded;
        }
        //require(escrow[1].recipient != msg.sender, "not recipient");
    }

    function release() external {
        require(escrow[1].creator == msg.sender, "not creator");
        (bool success, ) = payable(escrow[1].recipient).call{
            value: escrow[1].amount
        }("");
        if (!success) {
            revert transferfailed();
        }
    }
}
