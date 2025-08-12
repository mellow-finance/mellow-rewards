import csv
import os


labels = [f"distributions/lisk/{i}" for i in [1, 2]]

for label in labels:
    max_error = 0
    cumulative_error = 0
    for file_name in os.listdir(f"./{label}/local/"):
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

        with open(f"./{label}/external/{file_name}", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user = row["user"]
                reward = row["reward"]
                if user not in rewards:
                    print(f"User not found! file={file_name} user={user}")
                    continue
                error = int(rewards[user]) - int(reward)
                del rewards[user]
                if error == 0:
                    continue
                cumulative_error += error
                max_error = max(max_error, error)
    print(
        f"{label}: max error={max_error}, cumulative error={cumulative_error};"
    )
