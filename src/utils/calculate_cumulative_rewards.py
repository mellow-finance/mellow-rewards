import csv
import os
import json

s = "final_external_data/lsk_lsk_6_out.json final_external_data/lsk_lsk_7_out.json final_external_data/lsk_lsk_8_out.json final_external_data/lsk_lsk_9_out.json final_external_data/lsk_lsk_10_out.json final_external_data/lsk_lsk_11_out.json final_external_data/lsk_lsk_12_out.json final_external_data/lsk_rsmbtc_6_out.json final_external_data/lsk_rsmbtc_7_out.json final_external_data/lsk_rsmbtc_8_out.json final_external_data/lsk_rsmbtc_9_out.json final_external_data/lsk_rsmbtc_10_out.json final_external_data/lsk_rsmbtc_11_out.json final_external_data/lsk_rsmbtc_12_out.json final_external_data/lsk_wsteth_6_out.json final_external_data/lsk_wsteth_7_out.json final_external_data/lsk_wsteth_8_out.json final_external_data/lsk_wsteth_9_out.json final_external_data/lsk_wsteth_10_out.json final_external_data/lsk_wsteth_11_out.json final_external_data/lsk_wsteth_12_out.json"

vaults = {
    "wsteth": "0x1b10E2270780858923cdBbC9B5423e29fffD1A44",
    "lsk": "0x8cf94b5A37b1835D634b7a3e6b1EE02Ce7F0CD30",
    "mbtc": "0xa67E8B2E43B70D98E1896D3f9d563f3ABdB8Adcd",
    "rsmbtc": "0xa67E8B2E43B70D98E1896D3f9d563f3ABdB8Adcd",
}


previous_cumulative_data = {}

for key in vaults:
    previous_cumulative_data[key] = {}
    vault_address = vaults[key]

    path = f"distributions/lisk/5/merkle_proofs/{vault_address}.json"
    data = json.load(open(path, "r"))["data"]
    for item in data:
        previous_cumulative_data[key][item["address"]] = int(item["amount"])


for path in s.split():
    current_balances = {}
    name = path.replace("final_external_data/lsk_", "").replace("_out.json", "")
    token = name.split("_")[0]
    epoch = name.split("_")[1]
    with open(path, "r") as f:
        data = json.load(f)["data"]

        cumulative_rewards = {}
        for item in data:
            rewards = int(item["amount"])
            cumulative_rewards[item["address"]] = rewards
            current_balances[item["address"]] = rewards - previous_cumulative_data[
                token
            ].get(item["address"], 0)

        previous_cumulative_data[token] = cumulative_rewards.copy()

    os.makedirs(f'distributions/lisk/{epoch}/external', exist_ok=True)
    with open(f'distributions/lisk/{epoch}/external/{vaults[token]}.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['user', 'reward'])
        
        values = [(value, key) for key, value in current_balances.items()]
        values.sort(reverse=True)
        for value, key in values:
            if value > 0:
                writer.writerow([str(key), str(value)])
