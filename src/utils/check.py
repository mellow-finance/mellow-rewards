import csv
import os


labels = [f"distributions/lisk/{i}" for i in [1, 2, 3]]

for label in labels:
    for file_name in os.listdir(f"./{label}/local/"):
        max_error = 0
        cumulative_error = 0
        rewards = {}
        with open(f"./{label}/local/{file_name}", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user = row["user"]
                reward = row["reward"]
                if user in rewards:
                    print(f"Invalid user address! file={file_name} user={user}")
                    # exit(0)
                rewards[user] = reward

        external_rewards = {}

        with open(f"./{label}/external/{file_name}", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user = row["user"]
                reward = row["reward"]
                if user in external_rewards:
                    print(
                        f"Invalid external user address! file={file_name} user={user}"
                    )
                external_rewards[user] = reward

        users = sorted(
            list(
                set(
                    [key for key in rewards.keys()]
                    + [key for key in external_rewards.keys()],
                )
            )
        )
        
        for user in users:
            if user not in rewards:
                print(f'User not found (local): {user}')
            elif user not in external_rewards:
                print(f'User not found (external): {user}')
            else:
                error = int(rewards[user]) - int(external_rewards[user])
                if abs(error) > 100:
                    print(user, error)
                max_error = max(max_error, abs(error))
                cumulative_error += abs(error)

        print(
            f"{label}/{file_name}: max error={max_error}, cumulative error={cumulative_error};"
        )
