from utils.common import *

_CACHE_PATH = './src/services/velodrome_v3_cached_positions.csv'

class VelodromeV3Service(DeFiService):
    def __init__(
        self,
        w3: Web3,
        vault: str,
        pool: str,
        positions: Dict[int, Any],
        block_numbers: List[int],
    ):
        self.w3 = w3
        self.vault = vault
        self.pool = pool
        self.positions = positions
        self.block_numbers = block_numbers
        self.cache = dict()
        self.cached_block_number = 0
        self.cached_distributions = []

    def calculate_distributions(self, block_number: int) -> List[Tuple[str, int]]:
        if block_number < self.cached_block_number:
            raise Exception("VelodromeV3Service: block_number < cached_block_number")

        cached_index = -1
        current_index = -1
        for i in range(len(self.block_numbers)):
            if self.cached_block_number >= self.block_numbers[i]:
                cached_index = i
            if block_number >= self.block_numbers[i]:
                current_index = i

        if current_index == -1 or cached_index == current_index:
            return self.pool, self.cached_distributions

        pool_contract: Contract = self.w3.eth.contract(
            address=self.pool, abi=VELO_V3_POOL_ABI
        )
        multi_call: Contract = self.w3.eth.contract(
            address=MULTICALL_ADDRESS, abi=MULTICALL_ABI
        )
        token_index = (
            0
            if pool_contract.functions.token0().call().lower() == self.vault.lower()
            else 1
        )
        for i in range(cached_index + 1, current_index + 1):
            block_number = self.block_numbers[i]

            existing_token_ids = list(
                filter(
                    lambda token_id: self.positions[token_id]["mintedAt"]
                    <= block_number
                    < self.positions[token_id]["burntAt"],
                    self.positions.keys(),
                )
            )
            burnt_token_ids = list(
                filter(
                    lambda token_id: block_number
                    >= self.positions[token_id]["burntAt"],
                    self.positions.keys(),
                )
            )

            for token_id in burnt_token_ids:
                del self.positions[token_id]

            sqrt_price_x96 = pool_contract.functions.slot0().call(
                block_identifier=block_number
            )[0]

            # fees + principals
            calls = []
            for token_id in existing_token_ids:
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

            responses = multi_call.functions.tryAggregate(False, calls).call(
                block_identifier=block_number
            )

            for index in range(len(existing_token_ids)):
                fee_response = responses[index * 2]
                principal_response = responses[index * 2 + 1]
                token_id = existing_token_ids[index]
                if not fee_response[0] or not principal_response[0]:
                    raise Exception(
                        "VelodromeV3Service: SugarHeler call fails at tokenId={}, blockNumber={}".format(
                            token_id,
                            block_number,
                        )
                    )
                fees = decode(["uint256", "uint256"], fee_response[1])
                principals = decode(["uint256", "uint256"], principal_response[1])
                self.positions[token_id]["balance"] = (
                    fees[token_index] + principals[token_index]
                )

            # owner transfers
            for token_id in self.positions:
                position = self.positions[token_id]
                transfers = position["transfers"]
                if transfers and block_number in transfers:
                    self.positions[token_id]["owner"] = transfers[block_number]

        self.cached_block_number = block_number
        self.cached_distributions = list(
            filter(
                lambda item: item[1] > 0,
                [
                    (position["owner"], position["balance"])
                    for position in self.positions.values()
                ],
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
) -> Dict[int, Any]:
    cache = {}
    pool_events: List[Any] = call_blockscout_api(
        f"https://blockscout.lisk.com/api/v2/addresses/{pool}/logs"
    )
    block_numbers: List[int] = [int(event["block_number"]) for event in pool_events]
    all_positions: Dict[int, Any] = load_all_positions(
        w3, cache, block_numbers[0], to_block
    )
    positions = {}
    for token_id in all_positions:
        position = all_positions[token_id]
        if (
            position["token0"].lower() != vault.lower()
            and position["token1"].lower() != vault.lower()
        ):
            continue
        positions[token_id] = position

    for token_id in positions:
        transfers = call_blockscout_api(
            f"https://blockscout.lisk.com/api/v2/tokens/{VELO_V3_POSITION_MANAGER}/instances/{token_id}/transfers"
        )

        ownership_transfers = {}
        for transfer in transfers:
            sender = transfer["from"]["hash"]
            receiver = transfer["to"]["hash"]
            block_number = int(transfer["block_number"])
            block_numbers.append(block_number)
            if receiver == gauge:
                ownership_transfers[block_number] = sender
            else:
                ownership_transfers[block_number] = receiver
        burnt_at = to_block
        if transfers[-1]["to"]["hash"] == ZERO_ADDRESS:
            burnt_at = transfers[-1]["block_number"]

        positions[token_id]["owner"] = ZERO_ADDRESS
        positions[token_id]["balance"] = 0
        positions[token_id]["mintedAt"] = int(transfers[0]["block_number"])
        positions[token_id]["burntAt"] = int(burnt_at)
        positions[token_id]["transfers"] = ownership_transfers
    block_numbers = sorted(list(set(block_numbers)))
    return VelodromeV3Service(w3, vault, pool, positions, block_numbers)