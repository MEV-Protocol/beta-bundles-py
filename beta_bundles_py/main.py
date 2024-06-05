#!/usr/bin/env python

import os
import sys
import json
import time
import requests
import logging
from web3 import Web3, HTTPProvider
from eth_abi import encode
import coloredlogs

# Logging setup
log_level = logging.DEBUG
logger = logging.getLogger()
fmt = "%(name)-25s %(levelname)-8s %(message)s"
coloredlogs.install(level=log_level, fmt=fmt, logger=logger)

# Adjust logging levels for various libraries
logging.getLogger("web3.RequestManager").setLevel(logging.WARNING)
logging.getLogger("web3.providers.HTTPProvider").setLevel(logging.DEBUG)
logging.getLogger("requests").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def load_env_vars():
    """Load and validate required environment variables."""
    required_vars = [
        "RPC_L2", "BETA_BUNDLE_RPC", "AUCTIONEER", "BIDDER",
        "TX_ARGS", "TX_SIG", "CHAIN_ID", "CALLER", 
        "TX_TO", "TX_VALUE", "PRIVATE_KEY", "WEI_PER_GAS"
    ]
    
    for var in required_vars:
        if os.getenv(var) is None:
            logger.error(f"Missing required environment variable: {var}")
            sys.exit(1)

    env_vars = {var: os.getenv(var) for var in required_vars}
    return env_vars

# Initialize Web3 instances
env_vars = load_env_vars()
w3 = Web3(HTTPProvider(env_vars["RPC_L2"]))
w3_l1 = Web3(HTTPProvider(env_vars["BETA_BUNDLE_RPC"]))

def load_abi(file_path):
    """Load contract ABI from a JSON file."""
    try:
        with open(file_path) as f:
            return json.load(f)["abi"]
    except Exception as e:
        logger.error(f"Failed to load ABI from {file_path}: {e}")
        sys.exit(1)

auctioneer_abi = load_abi('abis/Auctioneer.json')
auctioneer = w3.eth.contract(address=env_vars["AUCTIONEER"], abi=auctioneer_abi)

bidder_abi = load_abi('abis/OpenBidder.json')
bidder = w3.eth.contract(address=env_vars["BIDDER"], abi=bidder_abi)

# Event signatures
sig_auction_closed = w3.keccak(text='AuctionSettled(uint256)').hex()
sig_auction_opened = w3.keccak(text='AuctionOpened(uint256,uint120)').hex()
sig_auction_paid = w3.keccak(text='AuctionPaidOut(uint256)').hex()
sig_auction_refunded = w3.keccak(text='AuctionRefund(uint256)').hex()

tx_global = None

def submit_bundle(slot: int, txs: list):
    """Submit a transaction bundle."""
    headers = {'Content-Type': 'application/json'}
    req = {
        "jsonrpc": "2.0",
        "method": "mev_sendBetaBundle",
        "params": [{"txs": txs, "slot": str(slot)}],
        "id": 1
    }
    try:
        response = requests.post(env_vars["BETA_BUNDLE_RPC"], headers=headers, data=json.dumps(req))
        response.raise_for_status()
        res = response.json()
        return res.get("result")
    except requests.RequestException as e:
        logger.error(f"Failed to submit bundle: {e}")
        return None

def build_transaction(slot):
    """Build and sign a transaction."""
    global tx_global
    try:
        args = json.loads(env_vars["TX_ARGS"])
        sig = env_vars["TX_SIG"]
        arg_types = sig[sig.find("(")+1:sig.find(")")].split(",")
        data = w3.keccak(text=sig)[:4] + encode(arg_types, args)
        
        block = w3_l1.eth.get_block('latest')
        base_fee = block.baseFeePerGas * 2
        
        transaction = {
            'chainId': int(env_vars["CHAIN_ID"]),
            'from': env_vars["CALLER"],
            'to': env_vars["TX_TO"],
            'value': int(env_vars["TX_VALUE"]),
            'nonce': w3_l1.eth.get_transaction_count(env_vars["CALLER"]),
            'maxPriorityFeePerGas': 0,
            'data': data,
            'gas': 1000000,
            'maxFeePerGas': base_fee
        }
        
        transaction["gas"] = w3_l1.eth.estimate_gas(transaction)
        signed = w3_l1.eth.account.sign_transaction(transaction, env_vars["PRIVATE_KEY"])
        tx_global = signed.rawTransaction.hex()
        
        logger.debug(f"Signed transaction: {tx_global}")
        hash = submit_bundle(slot, [tx_global])
        
        wei_per_gas = int(env_vars["WEI_PER_GAS"])
        tx = bidder.functions.openBid(wei_per_gas, transaction["gas"], hash).build_transaction({
            "from": env_vars["CALLER"],
            "value": wei_per_gas * transaction["gas"],
            "nonce": w3.eth.get_transaction_count(env_vars["CALLER"])
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=env_vars["PRIVATE_KEY"])
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception as e:
        logger.error(f"Failed to build transaction: {e}")

def handle_event(event):
    """Handle blockchain events."""
    global tx_global
    logger.info(event)
    
    try:
        if event["address"] == env_vars["AUCTIONEER"]:
            topic0 = event["topics"][0].hex()
            if topic0 == sig_auction_opened:
                slot = int(event["topics"][1].hex(), 16)
                logger.debug(f"Auction opened at slot {slot}")
                
                if not tx_global:
                    build_transaction(slot)
                else:
                    submit_bundle(slot, [tx_global])
                    logger.debug(f"Bundle submitted for slot {slot}")
            
            elif topic0 == sig_auction_closed:
                slot = int(event["topics"][1].hex(), 16)
                bal = auctioneer.functions.balanceOf(env_vars["BIDDER"], slot).call()
                logger.debug(f"Balance for slot {slot}: {bal}")
                
                if bal > 0:
                    tx = bidder.functions.submitBundles(slot).build_transaction({
                        "from": env_vars["CALLER"],
                        "nonce": w3.eth.get_transaction_count(env_vars["CALLER"])
                    })
                    signed_tx = w3.eth.account.sign_transaction(tx, private_key=env_vars["PRIVATE_KEY"])
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    w3.eth.wait_for_transaction_receipt(tx_hash)
            
            elif topic0 == sig_auction_paid:
                slot = int(event["topics"][1].hex(), 16)
                tx = bidder.functions.checkPendingBids(slot).build_transaction({
                    "from": env_vars["CALLER"],
                    "nonce": w3.eth.get_transaction_count(env_vars["CALLER"])
                })
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=env_vars["PRIVATE_KEY"])
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                exit_program("Block included. Check tx on L1")
            
            elif topic0 == sig_auction_refunded:
                slot = int(event["topics"][1].hex(), 16)
                tx = bidder.functions.checkPendingBids(slot).build_transaction({
                    "from": env_vars["CALLER"],
                    "nonce": w3.eth.get_transaction_count(env_vars["CALLER"])
                })
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=env_vars["PRIVATE_KEY"])
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                logger.info("Block missed. Trying for next auction slot.")
    except Exception as e:
        logger.error(f"Failed to handle event: {e}")

def exit_program(msg):
    """Exit the program with a message."""
    logger.info(msg)
    sys.exit(0)

def log_loop(poll_interval):
    """Main event polling loop."""
    while True:
        try:
            for event in w3.eth.get_logs({"fromBlock": "latest"}):
                handle_event(event)
            time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"Error in log loop: {e}")

def main():
    """Main function to start the log loop."""
    log_loop(2)

if __name__ == '__main__':
    main()
