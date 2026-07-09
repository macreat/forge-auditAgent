#!/usr/bin/env python3
"""Quick smoke-test: send a hello message to the local LLM server at localhost:8000."""

import httpx

URL = "http://localhost:8000/v1/chat/completions"

def main():
    payload = {
        "messages": [{"role": "user", "content": "Say hello in exactly one sentence."}],
        "temperature": 0.7,
        "max_tokens": 64,
    }
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(URL, json=payload)
            r.raise_for_status()
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
            print(f"[LLM] {reply}")
    except httpx.ConnectError:
        print("Error: Could not connect to localhost:8000. Is the server running?")
    except httpx.HTTPStatusError as e:
        print(f"HTTP error {e.response.status_code}: {e.response.text}")

if __name__ == "__main__":
    main()
