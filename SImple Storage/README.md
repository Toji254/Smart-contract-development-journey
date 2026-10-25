# Project Brief: Simple Storage Contract

## The request

I need a small Solidity smart contract that lets a user keep track of one numeric value on-chain. The value should remain available between interactions, and users should be able to check it and make changes through the contract.

This is an intentionally focused first project. I want a clear, dependable example of a contract that owns persistent state—not a full application, token, or account system.

## What I expect

The finished contract should let users:

- Find out the value the contract currently holds.
- Set the value to one they choose.
- Increase or decrease the value through separate actions.

Those actions should behave predictably. In particular, consider what should happen at numeric limits and make sure a decrease cannot produce an unintended result. Choose sensible behavior and make it clear in the contract.

## How I will judge the result

I should be able to deploy the contract, inspect its current value, and submit transactions that change that value. After each successful update, reading the contract again should show the new value. Invalid or impossible updates should not silently produce a misleading result.

Please keep the contract small and easy to understand. Use clear names, appropriate visibility, and Solidity features that fit the project's compiler version. Avoid adding features that are not needed for managing this single value.

## Your task

Implement the contract in this project and verify its behavior in a local or test environment. Include enough validation to demonstrate that reading, setting, increasing, and decreasing the value all work, including relevant boundary cases.

You have room to decide how best to structure the contract. The brief describes the outcome I need, not a line-by-line implementation recipe.

## Out of scope

This project does not need a user interface, access control, multiple stored values, token functionality, or a production deployment. Focus on delivering the requested contract and demonstrating that it behaves as expected.
