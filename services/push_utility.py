# For pushover

import os
import requests


def push(message):
    pushover_user = os.getenv("PUSHOVER_USER")
    pushover_token = os.getenv("PUSHOVER_TOKEN")
    pushover_url = "https://api.pushover.net/1/messages.json"
    print(pushover_user)
    print(pushover_token)

    print(f"Push: {message}")
    # payload = {
    #     "token": pushover_token,
    #     "user": pushover_user,
    #     "title": 'sample title',
    #     "message": message,
    #     "priority": 1
    # }
    payload = {"user": pushover_user, "token": pushover_token, "message": message}
    requests.post(pushover_url, data=payload)
