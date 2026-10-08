# MarkTrail local chain setup

This guide connects the application to the MarkTrailAudit contract on a local Anvil chain.

## 1. Start Anvil

~~~bash
anvil
~~~

Keep the terminal running.

Anvil prints test accounts and private keys. Use only those local development keys.

## 2. Build the contract

~~~bash
cd MarkTrail
forge build
~~~

## 3. Deploy the contract

Use one Anvil account as the owner and chain relayer.

~~~bash
forge create src/MarkTrailAudit.sol:MarkTrailAudit   --rpc-url http://127.0.0.1:8545   --private-key YOUR_ANVIL_PRIVATE_KEY
~~~

Copy the deployed contract address.

## 4. Authorize the relayer

The development application uses one server-side chain key for automated writes.

Authorize that address as both lecturer and reviewer on the local contract.

~~~bash
cast send CONTRACT_ADDRESS   "setLecturer(address,bool)"   RELAYER_ADDRESS true   --rpc-url http://127.0.0.1:8545   --private-key OWNER_PRIVATE_KEY

cast send CONTRACT_ADDRESS   "setReviewer(address,bool)"   RELAYER_ADDRESS true   --rpc-url http://127.0.0.1:8545   --private-key OWNER_PRIVATE_KEY
~~~

## 5. Configure MarkTrail

Export:

~~~bash
export MARKTRAIL_CHAIN_MODE=cast
export MARKTRAIL_CHAIN_RPC=http://127.0.0.1:8545
export MARKTRAIL_CONTRACT=CONTRACT_ADDRESS
export MARKTRAIL_CHAIN_PRIVATE_KEY=RELAYER_PRIVATE_KEY
~~~

Then start the application:

~~~bash
python3 run.py
~~~

Open:

http://127.0.0.1:8000

## 6. Confirm the connection

The top-right chain indicator should show a connected EVM chain.

Submit a batch as the lecturer.

The batch should move through:

~~~text
SUBMITTED
    ↓
on-chain commitment
    ↓
CONFIRMED
    ↓
reviewer verification
    ↓
VERIFIED
~~~

## Development warning

Do not put a real university private key into this environment.

The single server-side key is a deliberate MVP simplification.

A production deployment should use institutional key custody, rotation, monitoring, separation of duties, and an appropriate transaction-signing architecture.
