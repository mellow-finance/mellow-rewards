from utils.common import *
import json


class MorphoService(DeFiService):
    def __init__(
        self,
        w3: Web3,
        vault: str,
        morpho: str,
        positions: List[Tuple[str, str]],
        block_numbers: List[int],
    ):
        self.w3 = w3
        self.vault = vault
        self.morpho = morpho
        self.positions = positions
        self.block_numbers = block_numbers
        self.iterator = 0
        self.cached_block_number = 0
        self.cached_distributions = []

    def calculate_distributions(
        self, block_number: int
    ) -> Tuple[str, List[Tuple[str, int]]]:
        flag = False
        while (
            self.iterator < len(self.block_numbers)
            and self.block_numbers[self.iterator] <= block_number
        ):
            flag = True
            self.iterator += 1

        if not flag:
            return self.morpho, self.cached_distributions

        multi_call: Contract = self.w3.eth.contract(
            address=MULTICALL_ADDRESS, abi=MULTICALL_ABI
        )

        calls = []
        for position in self.positions:
            market_id, user_address = position
            calls.append(
                [self.morpho, "0x93c52062" + market_id[2:] + user_address[2:].zfill(64)]
            )
        results = multi_call.functions.tryAggregate(False, calls).call(
            block_identifier=block_number
        )
        positions = []
        cumulative_value = 0
        for index, result in enumerate(results):
            if not result[0]:
                continue
            data = decode(["uint256", "uint128", "uint128"], result[1])
            collateral = int(data[2])
            positions.append((self.positions[index][1], collateral))
            cumulative_value += collateral

        balances, _ = get_token_balances_onchain(
            self.vault, [self.morpho], block_number
        )
        if balances[0] != cumulative_value:
            raise Exception(
                "MorphoService: vault.balanceOf(morpho) != sum(position.collateral)"
            )

        self.cached_distributions = positions
        self.cached_block_number = block_number
        return self.morpho, self.cached_distributions


def collect_morpho_events(morpho: str):
    file_name = "./src/services/morpho_cached_events.json"
    data: List[Any] = json.load(open(file_name, "r"))
    max_recorded_block_number = 0
    for item in data:
        max_recorded_block_number = max(
            max_recorded_block_number, int(item["block_number"])
        )
    url = f"https://blockscout.lisk.com/api/v2/addresses/{morpho}/logs"
    responses = call_blockscout_api(
        url, limit_function=lambda x: x[0]["block_number"] <= max_recorded_block_number
    )

    for response in responses:
        data.append(
            {
                "address": response["address"]["hash"],
                "block_number": response["block_number"],
                "method_call": response["decoded"].get("method_call", ""),
                "parameters": {
                    item["name"]: item["value"]
                    for item in response["decoded"]["parameters"]
                },
            }
        )

    with open(file_name, "w") as f:
        json.dump(data, f, indent=2)
    return data


def create_morpho_service(
    w3: Web3, vault: str, morpho: str, from_block: int, to_block: int
):
    data = collect_morpho_events(morpho)

    market_ids = set()
    for item in data:
        if item["method_call"].startswith("CreateMarket"):
            if vault in item["parameters"]["marketParams"]:
                market_ids.add(item["parameters"]["id"])

    block_numbers = set()
    positions = set()
    target_events = [
        "Repay",
        "Withdraw",
        "WithdrawCollateral",
        "AccrueInterest",
        "Supply",
        "CreateMarket",
        "Liquidate",
        "Borrow",
        "SupplyCollateral",
    ]
    for item in data:
        method_call = item["method_call"].split("(")[0]
        if method_call in target_events:
            if item["parameters"]["id"] in market_ids:
                block_numbers.add(int(item["block_number"]))
                if "onBehalf" in item["parameters"]:
                    positions.add(
                        (item["parameters"]["id"], item["parameters"]["onBehalf"])
                    )

    return MorphoService(
        w3, vault, morpho, list(positions), sorted(list(block_numbers))
    )
