from common import *


class VelodromeV2Service(DeFiService):
    def __init__(
        self,
        w3: Web3,
        vault: str,
        pool: str,
        users: List[str],
        block_numbers: List[int],
    ):
        self.w3 = w3
        self.vault = vault
        self.pool = pool
        self.users = users
        self.block_numbers = block_numbers
        self.cached_block_number = 0
        self.cached_distributions = []

    def calculate_distributions(
        self, block_number: int
    ) -> Tuple[str, List[Tuple[str, int]]]:
        if block_number < self.cached_block_number:
            raise Exception("VelodromeV2Service: block_number < cached_block_number")
        current_index = -1
        cached_index = -1
        for i in range(len(self.block_numbers)):
            if self.cached_block_number >= self.block_numbers[i]:
                cached_index = i
            if block_number >= self.block_numbers[i]:
                current_index = i

        if current_index == -1 or cached_index == current_index:
            return self.pool, self.cached_distributions

        lp_balances, total_supply = get_token_balances_onchain(
            self.pool, self.users, block_number
        )
        if sum(lp_balances) != total_supply:
            raise Exception("VelodromeV2Service: sum(balances) != total_supply")
        self.cached_block_number = block_number
        self.cached_distributions = list(
            filter(
                lambda item: item[1] > 0,
                [
                    (
                        self.users[i],
                        lp_balances[i],
                    )
                    for i in range(len(lp_balances))
                ],
            )
        )
        return self.pool, self.cached_distributions


def create_velodrome_v2_service(w3: Web3, vault: str, pool: str) -> VelodromeV2Service:
    responses = call_blockscout_api(
        f"https://blockscout.lisk.com/api/v2/addresses/{pool}/logs"
    )
    block_numbers = set()
    users = set()
    for response in responses:
        block_numbers.add(int(response["block_number"]))
        if response["decoded"]["method_call"].startswith("Transfer"):
            for parameter in response["decoded"]["parameters"]:
                if parameter["name"] in ["from", "to"]:
                    users.add(parameter["value"])
    users = sorted(list(users))
    block_numbers = sorted(list(block_numbers))
    return VelodromeV2Service(w3, vault, pool, users, block_numbers)
