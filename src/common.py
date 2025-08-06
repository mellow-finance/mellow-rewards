from web3 import Web3
from web3.eth import Contract
from typing import List, Any, Dict, Set, Tuple
import requests
import csv
from eth_abi.abi import decode
import os
from random import randint
import time
from dotenv import load_dotenv

MULTICALL_ABI = [
    {
        "inputs": [
            {"internalType": "bool", "name": "requireSuccess", "type": "bool"},
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]",
            },
        ],
        "name": "tryAggregate",
        "outputs": [
            {
                "components": [
                    {"internalType": "bool", "name": "success", "type": "bool"},
                    {"internalType": "bytes", "name": "returnData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Result[]",
                "name": "returnData",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate",
        "outputs": [
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
            {"internalType": "bytes[]", "name": "returnData", "type": "bytes[]"},
        ],
        "stateMutability": "payable",
        "type": "function",
    },
]
VELO_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {
                "internalType": "uint16",
                "name": "observationCardinality",
                "type": "uint16",
            },
            {
                "internalType": "uint16",
                "name": "observationCardinalityNext",
                "type": "uint16",
            },
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]
VELO_V2_POOL_ABI = [
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint256", "name": "_reserve0", "type": "uint256"},
            {"internalType": "uint256", "name": "_reserve1", "type": "uint256"},
            {
                "internalType": "uint256",
                "name": "_blockTimestampLast",
                "type": "uint256",
            },
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

load_dotenv()
RPC_URL = os.getenv('LISK_RPC')
MULTICALL_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
VELO_V3_POSITION_MANAGER = "0x991d5546C4B442B4c5fdc4c8B8b8d131DEB24702"
SUGAR_ADDRESS = "0xB98fB4C9C99dE155cCbF5A14af0dBBAd96033D6f"
ZERO_ADDRESS = "0x" + "".zfill(40)

w3 = Web3(Web3.HTTPProvider(RPC_URL))


class DeFiService:
    def __init__(self):
        pass

    def calculate_distributions(
        self, block_number: int
    ) -> Tuple[str, List[Tuple[str, int]]]:
        pass


def call_blockscout_api(url: str) -> List[Any]:
    pagination = {}
    full_response = []
    while True:
        full_url = url
        separator = "?"
        for key, value in pagination.items():
            full_url += separator + key + "=" + str(value)
            separator = "&"
        response = None
        while True:
            try:
                response = requests.get(
                    full_url, headers={"accept": "application/json"}
                ).json()
                full_response.extend(response["items"])
                pagination = response["next_page_params"]
                break
            except Exception as e:
                print(e)
                print(full_url, response)
                time.sleep(1)
        if not pagination:
            break
    return full_response[::-1]


def get_token_balances_onchain(
    token: str, holders: List[str], block_number: int
) -> Tuple[List[int], int]:
    multi_call = w3.eth.contract(
        Web3.to_checksum_address(MULTICALL_ADDRESS), abi=MULTICALL_ABI
    )
    calls = [
        [
            token,
            "0x70a08231" + holder[2:].lower().zfill(64),
        ]
        for holder in holders
    ]
    calls.append([token, "0x18160ddd"])
    responses = multi_call.functions.aggregate(calls).call(
        block_identifier=block_number
    )
    balances = [int(response.hex(), 16) for response in responses[1]]
    return balances[:-1], balances[-1]
