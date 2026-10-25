# Project Brief: Token Sale

## The request

We are preparing a small, fixed-price sale of a new fungible token. We need a Solidity implementation that lets participants pay with ETH and receive the corresponding amount of our token. The token and sale should work together reliably, and the sale terms and accounting should be clear to both participants and the team operating it.

Treat this as a focused project, not a complete fundraising platform. We are looking for a working token and sale flow that can be exercised locally or on a test network.

## What we need

- A fungible token that follows the ERC-20 standard and can be distributed through the sale.
- A sale that exchanges ETH for the token at a defined rate.
- A clear way to tell whether the sale is open and whether tokens remain available.
- Accurate records of how much each participant has purchased and how many tokens have been sold overall.
- A way for the sale operator to recover proceeds and handle any unsold sale inventory after the sale has ended.

You may choose how to divide responsibilities between the token and sale contracts, and how the sale terms are configured. Make the resulting behavior understandable and avoid adding features beyond what this sale needs.

## Expected behavior

Participants should only be able to buy while the sale is active and while tokens are available. A successful purchase should deliver the correct token amount and update the relevant purchase and sale totals. Invalid purchases—including purchases outside the sale period, purchases that exceed the available inventory, and payments too small to receive any tokens—should fail clearly without leaving funds or accounting in an inconsistent state.

The team operating the sale should be able to access proceeds and unsold tokens only in a way that respects the sale's lifecycle. Consider who is authorized to perform those actions and when they may do so.

## How we will assess it

We should be able to deploy the contracts, configure or establish the sale terms, fund the sale with its token inventory, and complete a purchase using ETH. We should then be able to verify the buyer's token balance, the amount raised, and the number of tokens sold.

Please test both successful and unsuccessful cases. At minimum, demonstrate that purchases work at the intended rate, and that the sale rejects purchases when it is not active, has ended, or has no inventory left. Also check the handling of rounding, insufficient payments, and attempts to withdraw proceeds or unsold tokens at the wrong time or by an unauthorized account.

## Out of scope

This brief does not ask for a user interface, fiat payments, price feeds, investor verification, refunds, or a production launch. Keep the design focused on a fixed-price ETH sale, and make any assumptions about sale terms clear in your implementation and tests.

The brief describes the outcome we need, not a step-by-step implementation. Use your judgment to choose a clear design, and be prepared to explain the trade-offs.
