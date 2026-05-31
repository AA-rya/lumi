# Lumi

A personal AI companion built on AWS. Lumi remembers your conversations, learns about you over time, and lives entirely in your own cloud account.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Vanilla HTML/CSS/JS — open locally or serve statically |
| Backend | AWS Lambda (Python) with a public Function URL |
| AI | Amazon Bedrock — Nova Micro |
| Storage | DynamoDB (conversations + user profiles) |

## How to run

1. Open `index.html` in a browser (or `python -m http.server 8080` and visit `http://localhost:8080`)
2. Sign in with Google
3. Start chatting

The frontend talks directly to the Lambda Function URL — no extra server needed.

## Architecture

```
Browser (index.html)
    │
    └── HTTPS → Lambda Function URL (lumi-api, us-east-1)
                    ├── Auth: Google OAuth token verification
                    ├── Chat: Bedrock Nova Micro (us-east-1)
                    └── Storage: DynamoDB (us-east-2)
                         ├── lumi-users
                         └── lumi-conversations
```

## Setup (self-hosting)

1. Deploy `lambda_function.py` to AWS Lambda with a Function URL (auth: NONE)
2. Create DynamoDB tables `lumi-users` and `lumi-conversations` in us-east-2
3. Set Lambda environment variables:
   - `BEDROCK_API_KEY`
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` / `GOOGLE_USER_EMAIL`
4. Update the `LAMBDA_URL` constant in `index.html` to your function URL
5. Open `index.html`

## Redeploy Lambda

```bash
cd "amazon bedrock"
cp lambda_function.py package/
cd package && zip -r ../lambda.zip . && cd ..
rm package/lambda_function.py
aws lambda update-function-code --function-name lumi-api --zip-file fileb://lambda.zip --region us-east-1
```
