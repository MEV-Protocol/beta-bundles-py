#!/usr/bin/env python

from web3 import Web3, HTTPProvider
import time
import os
import json
import requests

# instantiate Web3 instance, connecting to L2
w3 = Web3(HTTPProvider(os.environ.get("L2_RPC", "https://holesky-api.securerpc.com/l2/")))
w3_l1 = Web3(HTTPProvider(os.environ.get("BETA_BUNDLE_RPC")))

f = open('abis/Auctioneer.json')
auctioneer_abi = json.load(f)["abi"]
auctioneer = w3.eth.contract(address=os.environ.get("AUCTIONEER"), abi=auctioneer_abi)
f.close()

f2 = open('abis/SettlementHouse.json')
settlement_abi = json.load(f2)["abi"]
settlement = w3.eth.contract(address=os.environ.get("SETTLEMENT"), abi=settlement_abi)
f2.close()

def submitBundle(slot: int, txs: list):
    # payload = "{\n  \"method\": \"manifold_sendBundle\",\n  \"id\": 1,\n  \"jsonrpc\": \"2.0\",\n  \"params\": [\n  {  \"txs\":  [\""+signedTxRaw+"\"] , \"blockNumber\":  \""+hex(chain.height + 10)+"\" }  ]\n}"
    headers = {'Content-Type': 'application/json'}

    req = {
        "jsonrpc": "2.0",
        "method": "mev_sendBetaBundle",
        "params": [
        {
            "txs": txs,
            "slot": str(slot)
        }
        ],
        "id": 1
    }
    response = requests.post(os.environ.get("BETA_BUNDLE_RPC"), headers=headers, data = json.dumps(req))
    # print(response)
    res = response.json()
    print(res)
    return res["result"]
    
    
def handle_event(event):
    # print(event)
    # print(event["address"])
    # print(os.environ.get("AUCTIONEER"))
    if event["address"] == os.environ.get("AUCTIONEER"):
        signature = w3.keccak(text='AuctionSettled(uint256)').hex()
        # print(signature)
        if signature == event["topics"][0].hex():
            # Auction settled, decode slot number
            slot = int(event["topics"][1].hex(), 16)
            # print(slot)
            # check futures balance
            bal = auctioneer.functions.balanceOf(os.environ.get("BIDDER"), slot).call()
            # print(bal)
            if bal > 0:
                # submit bundle
                # construct tx
                transaction = {
                    'chainId': 17000,
                    'from': os.environ.get("CALLER"),
                    'to': os.environ.get("CALLER"),
                    'value': 1000000000,
                    'nonce': w3_l1.eth.get_transaction_count(os.environ.get("CALLER")),
                    'gas': 50000,
                    'maxFeePerGas': 2000000000,
                    'maxPriorityFeePerGas': 1000000000,
                }
                # print(transaction)

                # 2. Sign tx with a private key
                signed = w3_l1.eth.account.sign_transaction(transaction, os.environ.get("PRIVATE_KEY"))
                print(signed.rawTransaction.hex())
                
                # submit bundle to rpc
                hash = submitBundle(slot, [signed.rawTransaction.hex()])
                print(hash)
                
                # finalise bundle submission on L2
                settlement.functions.submitBundle(slot, bal, [hash]).transact()

def log_loop(poll_interval):
    while True:
        for event in w3.eth.get_logs({"fromBlock": "latest",}):
            handle_event(event)
        time.sleep(poll_interval)

def main():
    log_loop(2)

if __name__ == '__main__':
    main()