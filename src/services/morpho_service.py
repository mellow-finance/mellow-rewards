from utils.common import *


class MorphoService(DeFiService):
    def __init__(
        self,
        w3: Web3,
        vault: str,
        morpho: str,
        users: List[str],
        block_numbers: List[int],
    ):
        self.w3 = w3
        self.vault = vault
        self.morpho = morpho
        self.users = users
        self.block_numbers = block_numbers
        self.cached_block_number = 0
        self.cached_distributions = []

    def calculate_distributions(
        self, block_number: int
    ) -> Tuple[str, List[Tuple[str, int]]]:

        pass


def create_morpho_service(
    w3: Web3, vault: str, morpho: str, from_block: int, to_block: int
):
    url = f"https://blockscout.lisk.com/api/v2/advanced-filters"
    responses = call_blockscout_api(
        url,
        {
            "transaction_types": "ERC-20",
            "token_contract_address_hashes_to_include": vault,
            "to_address_hashes_to_include": morpho,
            "from_address_hashes_to_include": morpho,
        },
    )

    block_numbers = []
    users = []
    for response in responses:
        block_numbers.append(int(response["block_number"]))
        users.append(response["from"]["hash"])
        users.append(response["to"]["hash"])
        tx_hash = response["hash"]
        logs = call_blockscout_api(
            f"https://blockscout.lisk.com/api/v2/transactions/{tx_hash}/logs"
        )
        for log in logs:
            if log["address"]["hash"].lower() == morpho.lower():
                print(log)
                print(log['block_number'])
                for parameter in log['decoded']['parameters']:
                    print(parameter['name'], parameter['value'])

    return MorphoService(
        w3, vault, morpho, sorted(list(set(users))), sorted(list(set(block_numbers)))
    )
