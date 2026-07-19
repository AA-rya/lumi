# Lumi

A personal AI companion built on AWS. Lumi remembers your conversations, learns about you over time, and lives entirely in your own cloud account.

## Run it

```bash
git clone https://github.com/AA-rya/lumi
cd lumi
chmod +x launch.sh && ./launch.sh
```

Opens `http://localhost:8080` automatically. Sign in with Google and start chatting.

> No install, no dependencies — just Python 3 (pre-installed on Mac/Linux).

## Stack

| Layer | Tech |
|---|---|
| Frontend | Vanilla HTML/CSS/JS, served locally |
| Backend | AWS Lambda (Python) via Function URL |
| AI | Amazon Bedrock — Nova Micro |
| Storage | DynamoDB (conversations + user profiles) |

## Architecture

```
Browser (index.html)
    │
    └── HTTPS → Lambda Function URL (lumi-api, us-east-1)
                    ├── Auth: Google OAuth
                    ├── Chat: Bedrock Nova Micro
                    └── Storage: DynamoDB (us-east-2)
                         ├── lumi-users
                         └── lumi-conversations
```

## Self-hosting (optional)

If you want to run this on your own AWS account:

1. Deploy `lambda_function.py` to AWS Lambda with a public Function URL (auth: NONE)
2. Create DynamoDB tables `lumi-users` and `lumi-conversations` in us-east-2
3. Set Lambda environment variables:
   - `BEDROCK_API_KEY`
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` / `GOOGLE_USER_EMAIL`
4. Update `LAMBDA_URL` in `index.html` to your function URL
5. Run `./launch.sh`

### Redeploy Lambda after changes

```bash
cp lambda_function.py package/
cd package && zip -r ../lambda.zip . && cd ..
rm package/lambda_function.py
aws lambda update-function-code --function-name lumi-api --zip-file fileb://lambda.zip --region us-east-1
```
commit
