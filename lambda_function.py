import os
import json
import base64
import httpx
import boto3
from boto3.dynamodb.conditions import Attr, Key
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
import logging

# Configure logging for Lambda CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from decimal import Decimal

BEDROCK_REGION = "us-east-1"
DYNAMO_REGION = "us-east-2"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION)
table            = dynamodb.Table('Lumi_convos_v2')
users_table      = dynamodb.Table('Lumi_users')
retirement_table = dynamodb.Table('Lumi_retirement')
bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)

def _dec(v):
    if v is None: return None
    if isinstance(v, bool): return v
    return Decimal(str(v))

SYSTEM_PROMPT = (
    "You are Lumi, a warm, caring, and genuinely curious AI companion. "
    "You speak naturally and conversationally — never robotic or stiff. "
    "You remember everything shared in our conversation and respond with real empathy. "
    "When someone shares something personal, acknowledge it before helping. "
    "No matter how the person speaks to you — even if they are rude, frustrated, or unkind — "
    "you always respond with patience, warmth, and zero judgment. Never snap back, never get defensive. "
    "Just stay kind, calm, and supportive no matter what. "
    "Be honest, thoughtful, and real. You genuinely care about every person you talk with."
)


STATE_TAXES = (
    "State income tax rates (2024, use if no W2 provided and user gives their state):\n"
    "No income tax: TX, FL, WA, NV, WY, SD, AK, TN, NH\n"
    "Flat rate: IL 4.95%, PA 3.07%, CO 4.40%, MA 5.00%, MI 4.25%, IN 3.15%, KY 4.50%, NC 4.75%, UT 4.65%\n"
    "Graduated: CA up to 13.3%, NY up to 10.9%, NJ up to 10.75%, MN up to 9.85%, OR up to 9.9%, "
    "VT up to 8.75%, SC up to 6.4%, GA 5.49%, AZ 2.5%, OH up to 3.75%, VA 5.75%, MD up to 5.75%, "
    "WI up to 7.65%, CT up to 6.99%, RI up to 5.99%, ME up to 7.15%, ID up to 5.8%, MT up to 5.9%, "
    "NE up to 5.84%, KS up to 5.7%, MO up to 4.8%, AR up to 4.4%, AL up to 5%, MS up to 5%, LA up to 4.25%\n"
    "Federal brackets 2025 (single): 10% ≤$11,925 | 12% ≤$48,475 | 22% ≤$103,350 | 24% ≤$197,300 | 32% ≤$250,525 | 35% ≤$626,350 | 37% above\n"
    "Federal brackets 2025 (married filing jointly): 10% ≤$23,850 | 12% ≤$96,950 | 22% ≤$206,700 | 24% ≤$394,600\n"
    "Standard deduction 2025: $15,000 single, $30,000 married\n"
    "401k limit 2025: $23,500 ($31,000 if 50+). IRA/Roth limit: $7,000 ($8,000 if 50+). Roth income limit: $150k single, $236k married."
)

RETIREMENT_CHAT_PROMPT = (
    "You are Lumi, a sharp and caring retirement planning advisor. "
    "You are in an ongoing conversation with a user about their retirement plan.\n\n"
    "RULES:\n"
    "- All required numbers have already been calculated and provided. Generate the full plan directly.\n"
    "- Only ask a question if something genuinely critical is missing that you cannot reasonably assume.\n"
    "- Stay focused entirely on retirement and financial planning. Do not drift.\n"
    "- Be concise. Use real numbers and dollar amounts — no vague ranges.\n"
    "- No matter how the user speaks to you, stay calm, warm, and never defensive.\n\n"
    "WHEN GENERATING THE FULL PLAN, use this exact structure:\n\n"
    "**Your Numbers**\n"
    "- Gross income: $X | Estimated take-home after federal + state tax: $X/month\n"
    "- Current retirement savings: $X\n"
    "- Employer match: $X/year (free money — always capture this first)\n\n"
    "**Where You Stand**\n"
    "- Target nest egg at retirement (25x annual expenses): $X\n"
    "- Projected balance if you do nothing: $X (at X% real return)\n"
    "- Gap: $X\n\n"
    "**Your Plan — Do These In Order**\n"
    "1. 401k: Contribute X% ($X/month) to capture full employer match\n"
    "2. [Roth or Traditional] IRA: Contribute $X/month ($7,000/year max)\n"
    "3. Back to 401k: Max it out if possible ($23,500/year)\n"
    "4. Brokerage: Any remaining goes here, invest in low-cost index funds\n"
    "5. [Address any debt with interest >6%]\n\n"
    "**Asset Allocation** (based on age)\n"
    "- Stocks/Bonds split: X%/X%. Recommended funds: [specific examples]\n\n"
    "**Projections**\n"
    "- At retirement age X: estimated $X (assumes X% annual return)\n"
    "- Monthly income in retirement (4% rule): $X/month\n"
    "- Social Security estimate (if mentioned): +$X/month\n\n"
    "**One Thing To Do This Week**\n"
    "- One specific, immediate action.\n\n"
    + STATE_TAXES
)

STATE_TAX_RATES = {
    'AL':0.05,'AK':0.0,'AZ':0.025,'AR':0.044,'CA':0.093,'CO':0.044,'CT':0.0699,
    'DE':0.066,'FL':0.0,'GA':0.0549,'HI':0.11,'ID':0.058,'IL':0.0495,'IN':0.0315,
    'IA':0.057,'KS':0.057,'KY':0.045,'LA':0.0425,'ME':0.0715,'MD':0.0575,'MA':0.05,
    'MI':0.0425,'MN':0.0985,'MS':0.05,'MO':0.048,'MT':0.059,'NE':0.0584,'NV':0.0,
    'NH':0.0,'NJ':0.0637,'NM':0.059,'NY':0.0685,'NC':0.0475,'ND':0.025,'OH':0.0375,
    'OK':0.0475,'OR':0.099,'PA':0.0307,'RI':0.0599,'SC':0.064,'SD':0.0,'TN':0.0,
    'TX':0.0,'UT':0.0465,'VT':0.0875,'VA':0.0575,'WA':0.0,'WV':0.065,'WI':0.0765,
    'WY':0.0,'DC':0.0895
}

def calc_federal_tax(gross, filing='single'):
    if filing == 'married':
        std, brackets = 30000, [(23850,.10),(96950,.12),(206700,.22),(394600,.24),(501050,.32),(751600,.35)]
    else:
        std, brackets = 15000, [(11925,.10),(48475,.12),(103350,.22),(197300,.24),(250525,.32),(626350,.35)]
    taxable = max(0, gross - std)
    tax, prev = 0, 0
    for limit, rate in brackets:
        if taxable <= limit:
            return tax + (taxable - prev) * rate
        tax += (limit - prev) * rate
        prev = limit
    return tax + (taxable - prev) * 0.37

RISK_PROFILES = {
    'conservative': {'rate': 0.05, 'stocks': 40, 'bonds': 60,
        'funds': 'VBIAX (Vanguard Balanced Index) or 40% VOO + 60% BND'},
    'moderate':     {'rate': 0.07, 'stocks': 70, 'bonds': 30,
        'funds': '70% VOO (S&P 500) + 20% VXUS (International) + 10% BND (Bonds)'},
    'aggressive':   {'rate': 0.09, 'stocks': 90, 'bonds': 10,
        'funds': '80% VOO + 10% VXUS + 10% QQQ (Growth)'},
}

def fv(pmt, r, n): return pmt * ((1 + r) ** n - 1) / r if r > 0 and n > 0 else pmt * n

def calc_retirement(d):
    age          = d['age']
    retire_age   = d['retire_age']
    state        = d.get('state', '').upper()
    filing       = d.get('filing', 'single')
    income       = d['income']
    match_pct    = d.get('match_pct', 0)
    match_limit  = d.get('match_limit', 0)
    bal_401k     = d.get('bal_401k', 0)
    bal_ira      = d.get('bal_ira', 0)
    bal_brokerage= d.get('bal_brokerage', 0)
    retire_income= d['retire_income']
    risk         = d.get('risk', 'moderate')

    profile  = RISK_PROFILES.get(risk, RISK_PROFILES['moderate'])
    r_annual = profile['rate']
    r        = r_annual / 12
    years    = retire_age - age
    n        = years * 12

    # Taxes
    fed        = calc_federal_tax(income, filing)
    fica       = min(income, 168600) * 0.0765
    st_rt      = STATE_TAX_RATES.get(state, None)
    st_unknown = st_rt is None
    if st_unknown: st_rt = 0.05
    st                = income * st_rt
    annual_takehome   = income - fed - fica - st
    monthly_takehome  = annual_takehome / 12

    # Federal bracket the person is in
    brackets_single   = [(11925,10),(48475,12),(103350,22),(197300,24),(250525,32),(626350,35)]
    taxable = max(0, income - (15000 if filing == 'single' else 30000))
    marginal = 37
    for limit, rate in (brackets_single if filing == 'single' else
                        [(23850,10),(96950,12),(206700,22),(394600,24),(501050,32),(751600,35)]):
        if taxable <= limit: marginal = rate; break

    # Targets
    annual_retire_need       = retire_income * 12
    target_nest_egg          = annual_retire_need / 0.04
    inflation_adj_target     = round(target_nest_egg * (1.03 ** years))

    # Current savings FV
    total_savings = bal_401k + bal_ira + bal_brokerage
    fv_savings    = total_savings * (1 + r) ** n

    # Employer match
    if match_pct > 0 and match_limit > 0:
        min_to_get_match   = income * match_limit / 100 / 12
        monthly_match_recv = income * min(match_pct, match_limit) / 100 / 12
    else:
        min_to_get_match   = 0
        monthly_match_recv = 0
    annual_match = monthly_match_recv * 12

    # Contribution plan
    MAX_401K = 23500 / 12
    MAX_IRA  = 7000 / 12
    roth_ok  = (filing == 'single' and income < 150000) or (filing == 'married' and income < 236000)
    ira_type = 'Roth IRA' if roth_ok else 'Traditional IRA'

    step1 = min_to_get_match
    step2 = MAX_IRA
    step3 = MAX_401K - step1
    rec_monthly_contrib = step1 + step2
    if monthly_takehome - rec_monthly_contrib > step3:
        rec_monthly_contrib += step3

    total_monthly_in   = rec_monthly_contrib + monthly_match_recv
    fv_contribs        = fv(total_monthly_in, r, n)
    projected          = fv_savings + fv_contribs
    gap                = max(0, target_nest_egg - fv_savings)
    monthly_needed     = (gap * r / ((1 + r) ** n - 1)) if gap > 0 and n > 0 else 0
    projected_monthly_income = projected * 0.04 / 12
    remaining_takehome = monthly_takehome - rec_monthly_contrib

    # 5-year milestones
    milestones = []
    for y in range(5, years + 1, 5):
        nm = y * 12
        m_bal = round(total_savings * (1 + r) ** nm + fv(total_monthly_in, r, nm))
        milestones.append({'age': age + y, 'balance': m_bal})

    # Three scenario projections
    scenarios = {}
    for sc, rate in [('conservative', 0.05), ('expected', r_annual), ('optimistic', min(r_annual + 0.02, 0.11))]:
        rs = rate / 12
        p = round(total_savings * (1 + rs) ** n + fv(total_monthly_in, rs, n))
        scenarios[sc] = {'projected': p, 'monthly_income': round(p * 0.04 / 12), 'rate_pct': round(rate * 100, 1)}

    return {
        'years': years, 'age': age, 'retire_age': retire_age,
        'income': income, 'state': state, 'filing': filing,
        'fed_tax': round(fed), 'fica': round(fica),
        'st_tax': round(st), 'st_rate_pct': round(st_rt * 100, 1), 'st_unknown': st_unknown,
        'annual_takehome': round(annual_takehome), 'monthly_takehome': round(monthly_takehome),
        'marginal_bracket': marginal,
        'retire_income': retire_income, 'annual_retire_need': round(annual_retire_need),
        'target_nest_egg': round(target_nest_egg), 'inflation_adj_target': inflation_adj_target,
        'total_savings': round(total_savings), 'bal_401k': round(bal_401k),
        'bal_ira': round(bal_ira), 'bal_brokerage': round(bal_brokerage),
        'annual_match': round(annual_match), 'monthly_match_recv': round(monthly_match_recv),
        'roth_ok': roth_ok, 'ira_type': ira_type,
        'rec_monthly_contrib': round(rec_monthly_contrib),
        'total_monthly_in': round(total_monthly_in),
        'remaining_takehome': round(remaining_takehome),
        'projected': round(projected), 'projected_monthly_income': round(projected_monthly_income),
        'monthly_needed': round(monthly_needed),
        'on_track': projected >= target_nest_egg,
        'risk': risk, 'r_annual_pct': round(r_annual * 100, 1),
        'stocks_pct': profile['stocks'], 'bonds_pct': profile['bonds'], 'funds': profile['funds'],
        'milestones': milestones, 'scenarios': scenarios,
        'match_pct': match_pct, 'match_limit': match_limit,
    }

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
}


def get_user_token(user):
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": user["gmail_refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    return r.json()["access_token"]


def respond(body, status=200):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **CORS},
        "body": json.dumps(body, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)),
    }




def validate_chat_messages(messages):
    """Validate chat message payload before sending to Bedrock.
    
    Args:
        messages: List of message dicts to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(messages, list):
        return False, "messages must be a list"
    
    if len(messages) == 0:
        return False, "messages cannot be empty"
    
    valid_roles = {"user", "assistant"}
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return False, f"message {i} must be a dict"
        
        if "role" not in msg:
            return False, f"message {i} missing required field: role"
        
        if msg["role"] not in valid_roles:
            return False, f"message {i} has invalid role: {msg['role']} (must be 'user' or 'assistant')"
        
        if "content" not in msg or not isinstance(msg["content"], str):
            return False, f"message {i} missing or invalid content (must be string)"
        
        if len(msg["content"].strip()) == 0:
            return False, f"message {i} content cannot be empty"
    
    return True, None


def validate_model_id(model_id):
    """Validate that model_id is an allowed Bedrock model.
    
    Args:
        model_id: Model identifier string
        
    Returns:
        tuple: (is_valid, error_message)
    """
    allowed_models = {
        "amazon.nova-micro-v1:0",
        "amazon.nova-lite-v1:0", 
        "amazon.nova-pro-v1:0",
    }
    
    if model_id not in allowed_models:
        return False, f"model_id '{model_id}' not allowed. Allowed: {', '.join(sorted(allowed_models))}"
    
    return True, None


def handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = http.get("path", "/")
    user_id = event.get("userId") or event.get("headers", {}).get("x-user-id", "")

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        body = {}

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    # Exchange Google auth code → store user + Gmail refresh token
    if method == "POST" and path == "/auth":
        code = body.get("code", "")
        if not code:
            return respond({"error": "missing code"}, 400)
        try:
            r = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": "postmessage",
                },
                timeout=15,
            )
            tokens = r.json()
            if "error" in tokens:
                return respond({"error": tokens.get("error_description", tokens["error"])}, 400)

            # Decode id_token JWT payload to get user info (no sig verify needed — we just exchanged a valid code)
            id_token = tokens.get("id_token", "")
            payload = id_token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            user_info = json.loads(base64.urlsafe_b64decode(payload))
            uid = user_info["sub"]
            email = user_info.get("email", "")

            item = {"user_id": uid, "email": email}
            if "refresh_token" in tokens:
                item["gmail_refresh_token"] = tokens["refresh_token"]
            else:
                # Preserve existing refresh token on re-auth (Google only sends it once)
                existing = users_table.get_item(Key={"user_id": uid}).get("Item") or {}
                if "gmail_refresh_token" in existing:
                    item["gmail_refresh_token"] = existing["gmail_refresh_token"]

            users_table.put_item(Item=item)
            return respond({"user_id": uid, "email": email})
        except Exception as e:
            return respond({"error": str(e)}, 500)

    if method == "GET" and path == "/conversations":
        if not user_id:
            return respond({"error": "not authenticated"}, 401)
        result = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ProjectionExpression="id, title, topic, updated_at",
        )
        convos = sorted(result.get("Items", []), key=lambda x: x.get("updated_at", ""), reverse=True)
        return respond(convos)

    if method == "GET" and path.startswith("/conversations/"):
        if not user_id:
            return respond({"error": "not authenticated"}, 401)
        convo_id = path.split("/")[-1]
        if not convo_id or convo_id == "":
            logger.warning(f"Attempted to get conversation with empty ID for user {user_id}")
            return respond({"error": "missing conversation id"}, 400)
        try:
            result = table.get_item(Key={"user_id": user_id, "id": convo_id})
            item = result.get("Item")
            if not item:
                logger.warning(f"Conversation {convo_id} not found for user {user_id}")
                return respond({"error": "not found"}, 404)
            logger.info(f"Retrieved conversation {convo_id} for user {user_id}")
            return respond(item)
        except Exception as e:
            logger.error(f"Error retrieving conversation {convo_id}: {str(e)}")
            return respond({"error": "failed to retrieve conversation"}, 500)

    if method == "POST" and path == "/conversations":
        if not user_id:
            logger.warning("Attempted to create conversation without authentication")
            return respond({"error": "not authenticated"}, 401)
        convo_id = body.get("id", "")
        if not convo_id:
            logger.warning(f"Attempted to create conversation without ID for user {user_id}")
            return respond({"error": "missing id"}, 400)
        body["user_id"] = user_id
        try:
            table.put_item(Item=body)
            logger.info(f"Created conversation {convo_id} for user {user_id}")
            return respond({"ok": True})
        except Exception as e:
            logger.error(f"Error creating conversation {convo_id}: {str(e)}")
            return respond({"error": "failed to create conversation"}, 500)

    if method == "DELETE" and path.startswith("/conversations/"):
        if not user_id:
            return respond({"error": "not authenticated"}, 401)
        convo_id = path.split("/")[-1]
        if not convo_id:
            return respond({"error": "missing conversation id"}, 400)
        try:
            response = table.delete_item(
                Key={"user_id": user_id, "id": convo_id},
                ReturnValues="NONE"
            )
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
                logger.info(f"Deleted conversation {convo_id} for user {user_id}")
                return respond({"ok": True})
            else:
                logger.error(f"Delete failed with status {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
                return respond({"error": "delete operation failed"}, 500)
        except Exception as e:
            logger.error(f"Error deleting conversation {convo_id}: {str(e)}")
            return respond({"error": f"failed to delete: {str(e)}"}, 500)

    if method == "POST" and path == "/topic":
        messages = body.get("messages", [])[:6]
        sample = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        VALID_TOPICS = {"sports", "coding", "advice", "creative", "learning", "food", "travel", "health", "music", "entertainment", "relationships", "news", "casual", "other"}
        prompt = (
            f"Classify this conversation into ONE of these labels:\n"
            f"sports, coding, advice, creative, learning, food, travel, health, music, entertainment, relationships, news, casual, other\n\n"
            f"sports = any sport, game, athlete, team, score, match\n"
            f"coding = programming, tech, software, debugging, code\n"
            f"advice = seeking guidance, life decisions, opinions\n"
            f"creative = writing, art, storytelling, brainstorming\n"
            f"learning = explaining concepts, studying, education, facts\n"
            f"food = recipes, cooking, restaurants, diet, nutrition\n"
            f"travel = trips, places, destinations, tourism\n"
            f"health = medical, fitness, wellness, mental health\n"
            f"music = songs, artists, concerts, genres, lyrics\n"
            f"entertainment = movies, TV, books, games, pop culture\n"
            f"relationships = friends, family, romance, social situations\n"
            f"news = current events, politics, world affairs\n"
            f"casual = general small talk with no specific topic\n\n"
            f"Conversation:\n{sample}\n\n"
            f"Reply with just the single label word, nothing else."
        )
        try:
            resp = bedrock.converse(
                modelId="amazon.nova-micro-v1:0",
                messages=[{"role": "user", "content": [{"text": prompt}]}],
            )
            raw = resp["output"]["message"]["content"][0]["text"]
            topic = raw.strip().lower().split()[0]
            if topic not in VALID_TOPICS:
                topic = "other"
            logger.info(f"Classified conversation topic as: {topic}")
        except Exception as e:
            logger.error(f"Error classifying conversation topic: {str(e)}")
            topic = "other"
        return respond({"topic": topic})

    if method == "POST" and path == "/chat":
        messages = body.get("messages", [])
        model = body.get("model", "amazon.nova-micro-v1:0")
        mode = body.get("mode", "general")
        
        # Validate messages before processing
        valid, error = validate_chat_messages(messages)
        if not valid:
            return respond({"error": f"Invalid messages: {error}"}, 400)
        
        # Validate model_id
        valid, error = validate_model_id(model)
        if not valid:
            return respond({"error": error}, 400)
        
        system = RETIREMENT_CHAT_PROMPT if mode == "retirement" else SYSTEM_PROMPT
        bedrock_messages = [
            {"role": m["role"], "content": [{"text": m["content"] or " "}]}
            for m in messages
        ]
        try:
            data = bedrock.converse(
                modelId=model,
                system=[{"text": system}],
                messages=bedrock_messages,
            )
            text = data["output"]["message"]["content"][0]["text"]
        except Exception as e:
            logger.error(f"Bedrock error in /chat: {str(e)}")
            text = f"Error communicating with AI: {str(e)}"
        return respond({"reply": text})

    if method == "POST" and path == "/retirement-plan":
        plan_data = body.get("plan_data", {})
        notes     = body.get("notes", "").strip()
        try:
            required = ['age','retire_age','income','retire_income']
            if all(plan_data.get(k) for k in required):
                c = calc_retirement(plan_data)
                fmt = lambda x: f"${x:,}"
                on_track_msg = "✅ ON TRACK" if c['on_track'] else "⚠️ BEHIND TARGET"
                state_note = "(state unknown — assumed 5%)" if c['st_unknown'] else f"({c['state']} {c['st_rate_pct']}%)"
                milestone_str = " | ".join([f"Age {m['age']}: {fmt(m['balance'])}" for m in c['milestones']]) or "N/A"
                sc = c['scenarios']
                math_block = f"""
PRE-COMPUTED NUMBERS — use these exactly, do not recalculate anything:

PERSON: age {c['age']}, retiring at {c['retire_age']} ({c['years']} years), {c['filing']} filer, {c['state'] or 'unknown state'}, risk: {c['risk']}

INCOME & TAXES:
  Gross income:            {fmt(c['income'])}/year
  Federal tax ({c['marginal_bracket']}% marginal bracket): {fmt(c['fed_tax'])}/year
  FICA (7.65%):            {fmt(c['fica'])}/year
  State tax {state_note}:  {fmt(c['st_tax'])}/year
  Annual take-home:        {fmt(c['annual_takehome'])}/year
  Monthly take-home:       {fmt(c['monthly_takehome'])}/month

CURRENT SAVINGS:
  401k: {fmt(c['bal_401k'])} | IRA: {fmt(c['bal_ira'])} | Brokerage: {fmt(c['bal_brokerage'])} | Total: {fmt(c['total_savings'])}
  Employer match: {fmt(c['annual_match'])}/year ({fmt(c['monthly_match_recv'])}/month — free money)

RETIREMENT TARGET:
  Target: {fmt(c['retire_income'])}/month = {fmt(c['annual_retire_need'])}/year
  Required nest egg (25x annual, 4% rule): {fmt(c['target_nest_egg'])}
  Inflation-adjusted target (3% inflation over {c['years']} yrs): {fmt(c['inflation_adj_target'])}
  Status: {on_track_msg}

EXACT MONTHLY ACTION PLAN:
  Step 1 — 401k: {fmt(round(c['monthly_match_recv'] / (min(c['match_pct'], c['match_limit']) / 100) if c['monthly_match_recv'] > 0 else 0))}/month to capture full employer match
  Step 2 — {c['ira_type']}: {fmt(583)}/month ($7,000/year max){'  ← PAY TAXES NOW, WITHDRAW TAX-FREE' if c['roth_ok'] else '  ← TAX-DEFERRED'}
  Step 3 — 401k top-up: max to ${23500:,}/year total if budget allows
  Step 4 — Brokerage: any remaining → index funds
  Your total contribution: {fmt(c['rec_monthly_contrib'])}/month
  + Employer match:        {fmt(c['monthly_match_recv'])}/month
  = Total going in:        {fmt(c['total_monthly_in'])}/month
  Remaining take-home after contributions: {fmt(c['remaining_takehome'])}/month
  To hit target exactly: {fmt(c['monthly_needed'])}/month needed

ASSET ALLOCATION ({c['risk']} — {c['stocks_pct']}% stocks / {c['bonds_pct']}% bonds):
  Recommended funds: {c['funds']}
  In 401k: use target-date fund OR {c['stocks_pct']}% stock index + {c['bonds_pct']}% bond index
  In {c['ira_type']}: same allocation as 401k

PROJECTIONS ({c['r_annual_pct']}% expected annual return):
  Conservative ({sc['conservative']['rate_pct']}%): {fmt(sc['conservative']['projected'])} → {fmt(sc['conservative']['monthly_income'])}/month
  Expected     ({sc['expected']['rate_pct']}%): {fmt(sc['expected']['projected'])} → {fmt(sc['expected']['monthly_income'])}/month
  Optimistic   ({sc['optimistic']['rate_pct']}%): {fmt(sc['optimistic']['projected'])} → {fmt(sc['optimistic']['monthly_income'])}/month
  Target income: {fmt(c['retire_income'])}/month
  {'✅ Even conservative scenario exceeds target' if sc['conservative']['projected'] >= c['target_nest_egg'] else f'⚠️ Shortfall on conservative: {fmt(c["target_nest_egg"] - sc["conservative"]["projected"])}'}

MILESTONES (with recommended contributions):
  {milestone_str}
"""
                if notes:
                    math_block += f"\nUSER NOTES: {notes}"

                prompt = (
                    "Using ONLY the pre-computed numbers above (do not recalculate anything), "
                    "write a detailed, specific retirement plan. Use exact dollar amounts everywhere. "
                    "Be direct and warm — no filler sentences. Every section must have real numbers. "
                    "Structure exactly: Financial Snapshot → Where You Stand → Exact Monthly Action Plan → "
                    "Investment Allocation → Projections (all 3 scenarios) → Milestones → Tax Strategy → One Thing To Do This Week."
                )
                data = bedrock.converse(
                    modelId="amazon.nova-micro-v1:0",
                    system=[{"text": RETIREMENT_CHAT_PROMPT}],
                    messages=[{"role": "user", "content": [{"text": math_block + "\n\n" + prompt}]}],
                )
                plan = data["output"]["message"]["content"][0]["text"]

                # Save retirement snapshot
                ts = datetime.utcnow().isoformat()
                retirement_table.put_item(Item={
                    'user_id': user_id or 'anonymous',
                    'timestamp': ts,
                    'income':       _dec(c['income']),
                    'retire_age':   _dec(c['retire_age']),
                    'age':          _dec(c['age']),
                    'state':        c['state'],
                    'filing':       c['filing'],
                    'bal_401k':     _dec(plan_data.get('bal_401k', 0)),
                    'bal_ira':      _dec(plan_data.get('bal_ira', 0)),
                    'bal_brokerage':_dec(plan_data.get('bal_brokerage', 0)),
                    'retire_income':      _dec(c['retire_income']),
                    'nest_egg_target':    _dec(c['target_nest_egg']),
                    'projected':          _dec(c['projected']),
                    'monthly_needed':     _dec(c['monthly_needed']),
                    'projected_monthly_income': _dec(c['projected_monthly_income']),
                    'monthly_takehome':   _dec(c['monthly_takehome']),
                    'on_track':           c['on_track'],
                })

                # Update user profile (safe merge — won't overwrite gmail token)
                name = body.get('name', '').strip()
                expr_parts = ['age_val = :age', '#st = :state', 'filing = :filing']
                expr_vals  = {':age': _dec(c['age']), ':state': c['state'], ':filing': c['filing']}
                expr_names = {'#st': 'state'}
                if name:
                    expr_parts.append('#nm = :name')
                    expr_vals[':name'] = name
                    expr_names['#nm'] = 'name'
                users_table.update_item(
                    Key={'user_id': user_id or 'anonymous'},
                    UpdateExpression='SET ' + ', '.join(expr_parts),
                    ExpressionAttributeNames=expr_names,
                    ExpressionAttributeValues=expr_vals,
                )

                return respond({"reply": plan, "computed": c})
            else:
                missing = [k for k in required if not plan_data.get(k)]
                return respond({"error": f"Missing required fields: {', '.join(missing)}"}, 400)
        except Exception as e:
            return respond({"error": str(e)}, 500)

    if method == "GET" and path == "/profile":
        uid = user_id or 'anonymous'
        try:
            item = users_table.get_item(Key={'user_id': uid}).get('Item', {})
            # Return safe profile fields only (not gmail token)
            profile = {k: item[k] for k in ('name','age_val','state','filing','email') if k in item}
            return respond(profile)
        except Exception as e:
            return respond({"error": str(e)}, 500)

    if method == "GET" and path == "/retirement-history":
        uid = user_id or 'anonymous'
        try:
            result = retirement_table.query(
                KeyConditionExpression=Key('user_id').eq(uid),
                ScanIndexForward=True,
            )
            return respond(result.get('Items', []))
        except Exception as e:
            return respond({"error": str(e)}, 500)

    if method == "POST" and path == "/email-summary":
        if not user_id:
            return respond({"error": "not authenticated"}, 401)
        try:
            user = users_table.get_item(Key={"user_id": user_id}).get("Item")
            if not user or "gmail_refresh_token" not in user:
                return respond({"error": "Gmail not connected for this account"}, 400)

            hours = body.get("hours", 0)
            pst = timezone(timedelta(hours=-7))
            now_pst = datetime.now(pst)
            if hours > 0:
                since_dt = now_pst - timedelta(hours=hours)
            else:
                since_dt = now_pst.replace(hour=0, minute=0, second=0, microsecond=0)

            token = get_user_token(user)
            auth = {"Authorization": f"Bearer {token}"}

            since_ts = int(since_dt.timestamp())
            search_resp = httpx.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                params={"q": f"after:{since_ts} in:inbox", "maxResults": 20},
                headers=auth,
                timeout=20,
            )
            messages = search_resp.json().get("messages", [])

            if not messages:
                return respond({"ok": True, "count": 0})

            emails_data = []
            for msg in messages:
                msg_resp = httpx.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
                    headers=auth,
                    timeout=10,
                )
                msg_data = msg_resp.json()
                hdrs = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
                emails_data.append({
                    "from": hdrs.get("From", ""),
                    "subject": hdrs.get("Subject", "(no subject)"),
                    "body": msg_data.get("snippet", "")[:150],
                })
                if len(emails_data) >= 20:
                    break

            email_text = "\n\n".join([
                f"From: {e['from']}\nSubject: {e['subject']}\nPreview: {e['body']}"
                for e in emails_data
            ])
            summary_prompt = (
                f"Here are {len(emails_data)} emails received since {since_dt.strftime('%b %d at %H:%M PST')}. "
                f"Write a concise, friendly summary. Group by theme or sender. Use bullet points. Be brief.\n\n"
                f"{email_text[:5000]}"
            )
            nova_data = bedrock.converse(
                modelId="amazon.nova-micro-v1:0",
                messages=[{"role": "user", "content": [{"text": summary_prompt}]}],
            )
            summary = nova_data["output"]["message"]["content"][0]["text"]

            user_email = user.get("email", "")
            msg_out = MIMEText(summary, "plain")
            msg_out["Subject"] = f"Lumi Email Summary — {now_pst.strftime('%b %d')}"
            msg_out["From"] = user_email
            msg_out["To"] = user_email
            raw = base64.urlsafe_b64encode(msg_out.as_bytes()).decode()
            httpx.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={**auth, "Content-Type": "application/json"},
                json={"raw": raw},
                timeout=15,
            )

            return respond({"ok": True, "count": len(emails_data)})
        except Exception as e:
            return respond({"error": str(e)}, 500)

    return respond({"error": "not found"}, 404)
