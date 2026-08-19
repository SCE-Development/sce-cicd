import requests

def create_paste(
    *,
    developer_key: str,
    content: str,
    timeout_seconds: float = 15.0,
) -> str:
    # Make sure the API key is not empty
    if not developer_key.strip():
        raise ValueError("Pastebin developer key cannot be empty")

    # Make sure there is actually something to upload
    if not content.strip():
        raise ValueError("Paste content cannot be empty")

    # Data Pastebin expects
    payload = {
        "api_dev_key": developer_key.strip(),
        "api_option": "paste",
        "api_paste_code": content,
    }

    # Send the POST request to Pastebin
    response = requests.post(
        "https://pastebin.com/api/api_post.php",
        data=payload,
        timeout=timeout_seconds,
    )

    response.raise_for_status()

    # Pastebin returns either:
    # - a Pastebin URL on success
    # - text starting with "Bad API request" on failure
    response_body = response.text.strip()

    if response_body.startswith("Bad API request"):
        raise RuntimeError(
            f"Pastebin rejected the request: {response_body}"
        )

    return response_body