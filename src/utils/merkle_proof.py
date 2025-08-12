from hexbytes import HexBytes
from web3 import Web3
from typing import List
from eth_abi import encode
import csv
import os
import json


def generate_merkle_tree(users: List[str], balances: List[int], reward_token: str):
    n = len(users)
    cache = [
        Web3.keccak(
            Web3.keccak(
                encode(
                    ["address", "address", "uint256"],
                    [users[i], reward_token, balances[i]],
                )
            )
        )
        for i in range(n)
    ]
    sorted_hashes = sorted(cache.copy())
    tree = [HexBytes(0x0) for _ in range(2 * n - 1)]
    for i in range(n):
        tree[len(tree) - 1 - i] = sorted_hashes[i]

    for i in range(n, 2 * n - 1):
        v = len(tree) - 1 - i
        left_hash = tree[v * 2 + 1]
        right_hash = tree[v * 2 + 2]
        if left_hash > right_hash:
            left_hash, right_hash = right_hash, left_hash
        tree[v] = Web3.keccak(encode(["bytes32", "bytes32"], [left_hash, right_hash]))

    root = tree[0]
    proofs = []
    for i in range(n):
        index = sorted_hashes.index(cache[i])
        tree_index = len(tree) - 1 - index
        proof = []
        while tree_index:
            sibling_index = tree_index
            if tree_index % 2 == 0:
                sibling_index -= 1
            else:
                sibling_index += 1
            proof.append(tree[sibling_index])
            tree_index = (tree_index - 1) >> 1
        proofs.append(proof)
    return root, proofs


def convert_to_str(value: HexBytes) -> str:
    if type(value) == HexBytes:
        result = value.hex()
        if not result.startswith("0x"):
            result = "0x" + result
        return result
    else:
        return str(result)


if __name__ == "__main__":
    labels = [f"./distributions/lisk/{i}/external" for i in [1, 2]]
    merkle_proofs_path = labels[-1].replace("external", "merkle_proofs")
    vaults = [
        "0x1b10E2270780858923cdBbC9B5423e29fffD1A44",
        "0x8cf94b5A37b1835D634b7a3e6b1EE02Ce7F0CD30",
        "0xa67E8B2E43B70D98E1896D3f9d563f3ABdB8Adcd",
    ]
    reward_token = "0xac485391EB2d7D88253a7F1eF18C37f4242D1A24"

    for vault in vaults:
        data = {}
        for label in labels:
            with open(f"{label}/{vault}.csv", "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    user = row["user"]
                    balance = int(row["reward"])
                    if user not in data:
                        data[user] = 0
                    data[user] += balance
        sorted_balances = sorted(
            [(balance, user) for user, balance in data.items()], reverse=True
        )
        users = []
        balances = []
        for i in range(len(sorted_balances)):
            balance, user = sorted_balances[i]
            users.append(user)
            balances.append(balance)

        merkle_root, proofs = generate_merkle_tree(users, balances, reward_token)
        data = {
            "root": convert_to_str(merkle_root),
            "data": [
                {
                    "address": users[i],
                    "reward": reward_token,
                    "amount": str(balances[i]),
                    "proof": [convert_to_str(x) for x in proofs[i]],
                }
                for i in range(len(users))
            ],
        }

        os.makedirs(f"{merkle_proofs_path}", exist_ok=True)
        with open(
            f"{merkle_proofs_path}/{vault}.json",
            "w",
        ) as f:
            json.dump(data, f, indent=2)
