from utils.common import *

_CACHE_PATH = "./src/services/velodrome_v3_cached_positions.csv"


class VelodromeV3Service(DeFiService):
    def __init__(
        self,
        w3: Web3,
        vault: str,
        pool: str,
        gauge: str,
        users: List[str],
        token_ids: List[int],
        block_numbers: List[int],
    ):
        self.w3 = w3
        self.vault = vault
        self.pool = pool
        self.gauge = gauge
        self.token_ids = token_ids
        self.users = users
        self.block_numbers = block_numbers
        self.cached_distributions = []
        self.iterator = 0
        self.pool_contract: Contract = self.w3.eth.contract(
            address=pool, abi=VELO_V3_POOL_ABI
        )
        self.token_index = (
            0
            if self.pool_contract.functions.token0().call().lower()
            == self.vault.lower()
            else 1
        )
        self.multi_call: Contract = self.w3.eth.contract(
            address=MULTICALL_ADDRESS, abi=MULTICALL_ABI
        )

    def name(self) -> str:
        return "VelodromeV3Service"

    def calculate_distributions(self, block_number: int) -> List[Tuple[str, int]]:
        flag = False
        while (
            self.iterator < len(self.block_numbers)
            and self.block_numbers[self.iterator] <= block_number
        ):
            flag = True
            self.iterator += 1

        if not flag:
            return self.pool, self.cached_distributions

        sqrt_price_x96 = self.pool_contract.functions.slot0().call(
            block_identifier=block_number
        )[0]

        # fees + principals + owners
        calls = []
        for token_id in self.token_ids:
            calls.append(
                [VELO_V3_POSITION_MANAGER, "0x6352211e" + hex(token_id)[2:].zfill(64)]
            )
            calls.append(
                [
                    SUGAR_ADDRESS,
                    "0x263a5362"
                    + VELO_V3_POSITION_MANAGER[2:].lower().zfill(64)
                    + hex(token_id)[2:].zfill(64),
                ]
            )
            calls.append(
                [
                    SUGAR_ADDRESS,
                    "0x22635397"
                    + VELO_V3_POSITION_MANAGER[2:].lower().zfill(64)
                    + hex(token_id)[2:].zfill(64)
                    + hex(sqrt_price_x96)[2:].zfill(64),
                ]
            )

        for account in self.users:
            calls.append([self.gauge, "0x4b937763" + account[2:].zfill(64)])

        responses = self.multi_call.functions.tryAggregate(False, calls).call(
            block_identifier=block_number
        )

        owner_of_staked = {}
        for i, user in enumerate(self.users):
            response = responses[i + len(self.token_ids) * 3]
            if not response[0]:
                continue
            staked_token_ids = decode(["uint256[]"], response[1])
            for token_ids in staked_token_ids:
                for token_id in token_ids:
                    owner_of_staked[token_id] = user

        balances = {}
        for index, token_id in enumerate(self.token_ids):
            owner_response = responses[index * 3]
            if not owner_response[0]:
                # nft does not exist
                continue

            fee_response = responses[index * 3 + 1]
            principal_response = responses[index * 3 + 2]
            if not fee_response[0] or not principal_response[0]:
                raise Exception(
                    "VelodromeV3Service: SugarHeler call fails at tokenId={}, blockNumber={}".format(
                        token_id,
                        block_number,
                    )
                )
            fees = decode(["uint256", "uint256"], fee_response[1])
            principals = decode(["uint256", "uint256"], principal_response[1])
            amount = fees[self.token_index] + principals[self.token_index]
            owner = Web3.to_checksum_address(decode(["address"], owner_response[1])[0])
            if owner == self.gauge:
                owner = owner_of_staked[token_id]
            if owner not in balances:
                balances[owner] = 0
            balances[owner] += amount

        self.cached_distributions = list(
            filter(
                lambda item: item[1] > 0,
                [(user, int(balance)) for user, balance in balances.items()],
            )
        )
        return self.pool, self.cached_distributions


def get_next_token_id_at(w3: Web3, cache: Dict[int, int], block_number: int) -> int:
    value = cache.get(block_number, 0)
    if not value:
        value = cache.get(
            block_number,
            int(
                w3.eth.get_storage_at(
                    VELO_V3_POSITION_MANAGER,
                    0x000000000000000000000000000000000000000000000000000000000000000F,
                    block_identifier=block_number,
                ).hex(),
                16,
            )
            % (1 << 176),
        )
        cache[block_number] = value
    return value


def convert_positions_response(token_id, response):
    position = decode(
        [
            "uint96",
            "address",
            "address",
            "address",
            "int24",
            "int24",
            "int24",
            "uint128",
            "uint256",
            "uint256",
            "uint128",
            "uint128",
        ],
        response,
    )
    return {
        "tokenId": token_id,
        "token0": position[2],
        "token1": position[3],
        "tickSpacing": position[4],
    }


def get_onchain_positions(
    multi_call: Contract, block_numbers: List[int], missing_token_ids: Set[int]
) -> Dict[int, Any]:
    block_numbers = sorted(list(set(block_numbers)))
    multi_call: Contract = w3.eth.contract(address=MULTICALL_ADDRESS, abi=MULTICALL_ABI)
    calls = []
    call_token_ids = []
    for token_id in missing_token_ids:
        calls.append(
            [
                VELO_V3_POSITION_MANAGER,
                "0x99fbab88" + hex(token_id)[2:].zfill(64),
            ]
        )
        call_token_ids.append(token_id)
    positions = dict()
    for block_number in block_numbers:
        responses = []
        step = 1000
        for i in range(0, len(calls), step):
            responses.extend(
                multi_call.functions.tryAggregate(False, calls[i : i + step]).call(
                    block_identifier=block_number
                )
            )
        for index, response in enumerate(responses):
            if response[0]:
                token_id = call_token_ids[index]
                positions[token_id] = convert_positions_response(token_id, response[1])

    return positions


def get_minting_block_number(
    w3: Web3, cache: Dict[int, int], from_block: int, to_block: int, token_id: int
) -> int:
    left = from_block
    right = to_block
    mid = 0
    answer = right
    while left <= right:
        mid = (left + right) >> 1
        next_token_id = get_next_token_id_at(w3, cache, mid)
        if next_token_id > token_id:
            answer = mid
            right = mid - 1
        else:
            left = mid + 1
    return answer


def load_all_positions(
    w3: Web3, cache: Dict[int, int], from_block: int, to_block: int
) -> Dict[int, Any]:
    positions = {}

    with open(_CACHE_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            positions[int(row["tokenId"])] = row

    from_token_id = get_next_token_id_at(w3, cache, from_block - 1)
    to_token_id = get_next_token_id_at(w3, cache, to_block)

    missing_token_ids = set()
    for token_id in range(from_token_id, to_token_id):
        if token_id not in positions:
            missing_token_ids.add(token_id)

    if not missing_token_ids:
        return positions

    multi_call: Contract = w3.eth.contract(address=MULTICALL_ADDRESS, abi=MULTICALL_ABI)
    collected_onchain_positions = get_onchain_positions(
        multi_call,
        sorted(
            list(set([randint(from_block, to_block) for _ in range(50)] + [to_block]))
        ),
        missing_token_ids,
    )

    for token_id in collected_onchain_positions:
        if token_id in missing_token_ids:
            missing_token_ids.remove(token_id)
            positions[token_id] = collected_onchain_positions[token_id]

    missing_token_ids = sorted(list(missing_token_ids))
    missing_token_ids_iterator = 0
    while missing_token_ids_iterator < len(missing_token_ids):
        print(
            "Processing {}/{}...".format(
                missing_token_ids_iterator + 1, len(missing_token_ids)
            )
        )
        block_number = get_minting_block_number(
            w3,
            cache,
            from_block,
            to_block,
            missing_token_ids[missing_token_ids_iterator],
        )
        calls = []

        call_token_ids = []
        for token_id in range(
            get_next_token_id_at(w3, cache, block_number - 1),
            get_next_token_id_at(w3, cache, block_number),
        ):
            if missing_token_ids_iterator == len(missing_token_ids):
                break
            if token_id == missing_token_ids[missing_token_ids_iterator]:
                calls.append(
                    [
                        VELO_V3_POSITION_MANAGER,
                        "0x99fbab88" + hex(token_id)[2:].zfill(64),
                    ]
                )
                call_token_ids.append(token_id)
                missing_token_ids_iterator += 1
        if not calls:
            continue
        responses = multi_call.functions.tryAggregate(False, calls).call(
            block_identifier=block_number
        )
        for index, response in enumerate(responses):
            token_id = call_token_ids[index]
            if response[0]:
                positions[token_id] = convert_positions_response(token_id, response[1])
            else:
                positions[token_id] = {
                    "tokenId": token_id,
                    "token0": ZERO_ADDRESS,
                    "token1": ZERO_ADDRESS,
                    "tickSpacing": 0,
                }

    with open(_CACHE_PATH, "w") as f:
        writer = csv.writer(f)
        writer.writerow(["tokenId", "token0", "token1", "tickSpacing"])
        for position in positions.values():
            writer.writerow(
                [
                    position["tokenId"],
                    position["token0"],
                    position["token1"],
                    position["tickSpacing"],
                ]
            )

    return positions


def create_velodrome_v3_service(
    w3: Web3,
    vault: str,
    pool: str,
    gauge: str,
    to_block: int,
) -> DeFiService:
    cache = {}
    pool_events: List[Any] = call_blockscout_api(
        f"https://blockscout.lisk.com/api/v2/addresses/{pool}/logs"
    )
    block_numbers: List[int] = [int(event["block_number"]) for event in pool_events]
    all_positions: Dict[int, Any] = load_all_positions(
        w3, cache, block_numbers[0], to_block
    )
    pool_contract = w3.eth.contract(address=pool, abi=VELO_V3_POOL_ABI)
    pool_token0 = pool_contract.functions.token0().call().lower()
    pool_token1 = pool_contract.functions.token1().call().lower()
    pool_tick_spacing = pool_contract.functions.tickSpacing().call()
    token_ids = set()
    for token_id, position in all_positions.items():
        if (
            position["token0"].lower() != pool_token0
            or position["token1"].lower() != pool_token1
            or int(position["tickSpacing"]) != int(pool_tick_spacing)
        ):
            continue
        token_ids.add(token_id)

    users = set()
    for token_id in token_ids:
        transfers = call_blockscout_api(
            f"https://blockscout.lisk.com/api/v2/tokens/{VELO_V3_POSITION_MANAGER}/instances/{token_id}/transfers"
        )
        for transfer in transfers:
            users.add(transfer["from"]["hash"])
            users.add(transfer["to"]["hash"])
            block_numbers.append(int(transfer["block_number"]))

    users = sorted(list(users))
    block_numbers = sorted(list(set(block_numbers)))
    return VelodromeV3Service(w3, vault, pool, gauge, users, token_ids, block_numbers)
