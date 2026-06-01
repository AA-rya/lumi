import os
import httpx

API_KEY = os.environ.get("BEDROCK_API_KEY", "your-api-key-here")
REGION = "us-east-1"

response = httpx.get(
    f"https://bedrock-runtime.{REGION}.amazonaws.com/v1/models",
    headers={
        "Authorization": f"Bearer {API_KEY}",
    },
    timeout=30,
)

print("Status:", response.status_code)
print("Response:", response.text)
