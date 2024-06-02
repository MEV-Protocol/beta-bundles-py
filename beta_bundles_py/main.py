#!/usr/bin/env python

from web3 import Web3, HTTPProvider
from eth_abi import encode
import time
import os
import json
import requests
import logging
import coloredlogs

log_level=logging.DEBUG
# """Setup root logger and quiet some levels."""
logger = logging.getLogger()

# Set log format to display the logger name to hunt down verbose logging modules
fmt = "%(name)-25s %(levelname)-8s %(message)s"

# Use colored logging output for console with the coloredlogs package
# https://pypi.org/project/coloredlogs/
coloredlogs.install(level=log_level, fmt=fmt, logger=logger)

# Disable logging of JSON-RPC requests and replies
logging.getLogger("web3.RequestManager").setLevel(logging.WARNING)
logging.getLogger("web3.providers.HTTPProvider").setLevel(logging.DEBUG)
# logging.getLogger("web3.RequestManager").propagate = False

# Disable all internal debug logging of requests and urllib3
# E.g. HTTP traffic
logging.getLogger("requests").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# instantiate Web3 instance, connecting to L2
w3 = Web3(HTTPProvider(os.environ.get("RPC_L2", "https://holesky-api.securerpc.com/l2/")))
w3_l1 = Web3(HTTPProvider(os.environ.get("BETA_BUNDLE_RPC")))

f = open('abis/Auctioneer.json')
auctioneer_abi = json.load(f)["abi"]
auctioneer = w3.eth.contract(address=os.environ.get("AUCTIONEER"), abi=auctioneer_abi)
f.close()

f3 = open('abis/OpenBidder.json')
bidder_abi = json.load(f3)["abi"]
bidder = w3.eth.contract(address=os.environ.get("BIDDER"), abi=bidder_abi)
f3.close()

sig_auction_closed = w3.keccak(text='AuctionSettled(uint256)').hex()
sig_auction_opened = w3.keccak(text='AuctionOpened(uint256,uint120)').hex()

def submitBundle(slot: int, txs: list):
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
    res = response.json()
    return res["result"]
    
    
def handle_event(event):
    logger.info(event)
    if event["address"] == os.environ.get("AUCTIONEER"):
        if sig_auction_opened == event["topics"][0].hex():
            # auction opened
            slot = int(event["topics"][1].hex(), 16)
            logger.debug(slot)
            # build private tx from env vars
            args = json.loads(os.environ.get("TX_ARGS"))
            logger.debug(args)
            sig = os.environ.get("TX_SIG")
            x = sig.find("(")
            y = sig.find(")")
            arg_types = sig[x+1:y].split(",")
            logger.debug(arg_types)
            data = w3.keccak(text=sig)[0:4] + encode(arg_types, args) 
            logger.debug(data)
            # construct tx
            block = w3_l1.eth.get_block('latest')
            base_fee = block.baseFeePerGas * 2
            transaction = {
                'chainId': int(os.environ.get("CHAIN_ID")),
                'from': os.environ.get("CALLER"),
                'to': os.environ.get("TX_TO"),
                'value': int(os.environ.get("TX_VALUE")),
                'nonce': w3_l1.eth.get_transaction_count(os.environ.get("CALLER")),
                'maxPriorityFeePerGas': 0,
                'data': data,
                'gas': 1000000,
                'maxFeePerGas': base_fee
            }
            logger.debug(transaction)
            # cannot estimate gas as 
            amount_of_gas = w3_l1.eth.estimate_gas(transaction)
            transaction["gas"] = amount_of_gas

            # Sign tx with a private key
            signed = w3_l1.eth.account.sign_transaction(transaction, os.environ.get("PRIVATE_KEY"))
            logger.debug(signed.rawTransaction.hex())
            
            # submit bundle to rpc
            hash = submitBundle(slot, [signed.rawTransaction.hex()])
            logger.debug(hash)
            # open bid on OpenBidder contract
            wei_per_gas = int(os.environ.get("WEI_PER_GAS"))
            tx = bidder.functions.openBid(wei_per_gas, amount_of_gas, hash).build_transaction({"from": os.environ.get("CALLER"), "value": wei_per_gas * amount_of_gas, "nonce": w3.eth.get_transaction_count(os.environ.get("CALLER"))})
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=os.environ.get("PRIVATE_KEY"))
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
        elif sig_auction_closed == event["topics"][0].hex():
            # Auction settled, decode slot number
            slot = int(event["topics"][1].hex(), 16)
            # check futures balance
            bal = auctioneer.functions.balanceOf(os.environ.get("BIDDER"), slot).call()
            logger.debug(bal)
            if bal > 0:
                # finalise bundle submission on L2
                tx = bidder.functions.submitBundles(slot).build_transaction({"from": os.environ.get("CALLER"), "nonce": w3.eth.get_transaction_count(os.environ.get("CALLER"))})
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=os.environ.get("PRIVATE_KEY"))
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)

def log_loop(poll_interval):
    while True:
        for event in w3.eth.get_logs({"fromBlock": "latest",}):
            handle_event(event)
        time.sleep(poll_interval)

def main():
    log_loop(2)

if __name__ == '__main__':
    main()
