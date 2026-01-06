import os
import dotenv
import requests
dotenv.load_dotenv()



SMEE_URL = os.getenv("SMEE_URL") or "https://smee.io/YOUR_CHANNEL"
PAYLOAD = {"ref": "refs/heads/main", "repository": {"name": "lit-workshop"}}


def main():
    if "YOUR_CHANNEL" in SMEE_URL:
        print("Set SMEE_URL or replace SMEE_URL variable in this file.")
        return

    headers = {"Content-Type": "application/json", "X-GitHub-Event": "push"}
    response = requests.post(SMEE_URL, headers=headers, json=PAYLOAD, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text or '<empty>'}")


if __name__ == "__main__":
    main()
