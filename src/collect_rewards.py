from utils.common import *

from services.velodrome_v2_service import create_velodrome_v2_service
from services.velodrome_v3_service import create_velodrome_v3_service
from services.morpho_service import create_morpho_service
from services import constants


def calculate_rewards(
    vault: str,
    withdrawal_queue: str,
    service_init_params: List[Tuple[str, List[Any]]],
    from_block: int,
    to_block: int,
    reward_amount: int,
    label: str,
) -> None:
    print(f"Collecting vault ({vault}) transfer events...")
    responses = call_blockscout_api(
        f"https://blockscout.lisk.com/api/v2/tokens/{vault}/transfers"
    )
    transfers = sorted(
        list(
            map(
                lambda x: {
                    "from": x["from"]["hash"],
                    "to": x["to"]["hash"],
                    "amount": int(x["total"]["value"]),
                    "block_number": int(x["block_number"]),
                },
                responses,
            )
        ),
        key=lambda x: x["block_number"],
    )

    service_mapping = {
        constants.VELODROME_V2: create_velodrome_v2_service,
        constants.VELODROME_V3: create_velodrome_v3_service,
        constants.MORPHO: create_morpho_service,
    }

    print("Creating services...")
    services: List[DeFiService] = []
    for service_type, service_data in service_init_params:
        services.append(service_mapping[service_type](w3, vault, *service_data))

    cumulative_balances = {}
    user_balances = {}
    transfer_iterator = 0
    print("Processing...")
    for block_number in range(transfers[0]["block_number"], to_block + 1):
        while (
            transfer_iterator < len(transfers)
            and transfers[transfer_iterator]["block_number"] == block_number
        ):
            transfer = transfers[transfer_iterator]
            sender = transfer["from"]
            receiver = transfer["to"]
            if sender != ZERO_ADDRESS:
                user_balances[sender] = (
                    user_balances.get(sender, 0) - transfer["amount"]
                )
            if receiver != ZERO_ADDRESS:
                user_balances[receiver] = (
                    user_balances.get(receiver, 0) + transfer["amount"]
                )
            transfer_iterator += 1

        if block_number >= from_block:
            run_checks = (
                block_number - from_block
            ) % 5000 == 0 or block_number == to_block
            if run_checks:
                print("Processing {} / {}...".format(block_number, to_block))
                onchain_balances, total_supply = get_token_balances_onchain(
                    vault, list(user_balances.keys()), block_number
                )
                if sum(onchain_balances) != total_supply:
                    raise Exception("total supply != sum(onchain balances)")
                for index, (user, balance) in enumerate(user_balances.items()):
                    if onchain_balances[index] != balance:
                        raise Exception("user balance != onchain user balance")

            defi_pool_shares = {}
            for service in services:
                defi_pool, distributions = service.calculate_distributions(block_number)
                defi_pool_shares[defi_pool] = distributions

            for holder, balance in user_balances.items():
                if holder in defi_pool_shares:
                    distributions = defi_pool_shares[holder]
                    total_defi_shares = sum(
                        [defi_shares for _, defi_shares in distributions]
                    )
                    for defi_user, defi_shares in distributions:
                        if defi_user not in cumulative_balances:
                            cumulative_balances[defi_user] = 0
                        cumulative_balances[defi_user] += (
                            balance * defi_shares // total_defi_shares
                        )
                else:
                    if holder not in cumulative_balances:
                        cumulative_balances[holder] = 0
                    cumulative_balances[holder] += balance

    del cumulative_balances[Web3.to_checksum_address(withdrawal_queue)]

    total_cumulative_balances = sum(cumulative_balances.values())

    rewards = sorted(
        list(
            filter(
                lambda item: item[1] > 0,
                map(
                    lambda item: (
                        item[0],
                        item[1] * 10**18 * reward_amount // total_cumulative_balances,
                    ),
                    cumulative_balances.items(),
                ),
            )
        ),
        key=lambda item: -item[1],
    )

    os.makedirs(f"./{label}", exist_ok=True)
    with open(f"./{label}/{vault}.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerow(["user", "reward"])
        for user, amount in rewards:
            writer.writerow([user, amount])


if __name__ == "__main__":
    from_block = 19577605
    to_block = 19880004

    label = "./distributions/lisk/3/local"
    calculate_rewards(
        "0x1b10E2270780858923cdBbC9B5423e29fffD1A44",
        "0x5E3584d67b86f0C77FB43073A1238a943CA26188",
        [
            (constants.VELODROME_V2, ["0xDcb60949A0cCFc813A0D8dF8e8Ebcac097a1A9d1"]),
            (
                constants.VELODROME_V3,
                [
                    "0x9788ABD076014dE9c04A2283c709BfF7778a6cF1",
                    "0xcf3c93f6FAb70b39F862ceD14A7c84e6aE319328",
                    to_block,
                ],
            ),
            (
                constants.MORPHO,
                ["0x00cD58DEEbd7A2F1C55dAec715faF8aed5b27BF8", from_block, to_block],
            ),
        ],
        from_block,
        to_block,
        4000,
        label,
    )

    calculate_rewards(
        "0xa67E8B2E43B70D98E1896D3f9d563f3ABdB8Adcd",
        "0x8294c6B7ed0dEf4Bcf0c1a34c9A09Fe0880D8A13",
        [
            (constants.VELODROME_V2, ["0x7d8a904165ee7D6DcD70d2680D713C2984473B45"]),
            (
                constants.VELODROME_V3,
                [
                    "0x9665Df2b69163411D9b089F6C192F8CeB579FB57",
                    "0x7a0CA233A1599a1b1d23563326a4C560Ef1f4B33",
                    to_block,
                ],
            ),
            (
                constants.MORPHO,
                ["0x00cD58DEEbd7A2F1C55dAec715faF8aed5b27BF8", from_block, to_block],
            ),
        ],
        from_block,
        to_block,
        8000,
        label,
    )

    calculate_rewards(
        "0x8cf94b5A37b1835D634b7a3e6b1EE02Ce7F0CD30",
        "0x025e059BCea0eAdBb58b16db7D2e5748736F6511",
        [
            (
                constants.VELODROME_V3,
                [
                    "0xFF457eFE9A906CB4af830C22c2B36f15a9a77619",
                    "0xD3AD131b12699c464dFD461a5FcE225F2C2e410b",
                    to_block,
                ],
            ),
            (
                constants.MORPHO,
                ["0x00cD58DEEbd7A2F1C55dAec715faF8aed5b27BF8", from_block, to_block],
            ),
        ],
        from_block,
        to_block,
        500,
        label,
    )
