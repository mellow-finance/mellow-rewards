import csv
import os

label = 'distributions/lisk/LSK_second_batch'

for file_name in os.listdir(label):
    rewards = {}
    with open(f"./{label}/{file_name}", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            user = row["user"]
            reward = row["reward"]
            if user in rewards:
                print(f"Invalid user address! file={file_name} user={user}")
                # exit(0)
            rewards[user] = reward

    with open(f"./{label}_external_collector/{file_name}", "r") as f:
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
            print(f'Error file={file_name}, user={user}, error={error}')
