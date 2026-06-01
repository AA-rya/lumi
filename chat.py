import os
import httpx

API_KEY = os.environ.get("BEDROCK_API_KEY", "your-api-key-here")
REGION = "us-east-1"

MODEL = "amazon.nova-micro-v1:0"

response = httpx.post(
    f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{MODEL}/converse",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "messages": [
            {"role": "user", "content": [{"text": "Hello, how are you?"}]}
        ]
    },
    timeout=30,
)

print("Status:", response.status_code)
print("Response:", response.text)
