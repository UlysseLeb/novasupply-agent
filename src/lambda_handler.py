"""Point d'entrée Lambda, derrière API Gateway (HTTP API).

Auth par header X-API-Key, même patron que pme-rag-chatbot et novasupply-inbox-ai :
vérification manuelle dans le handler plutôt qu'un Usage Plan API Gateway natif
(fonctionnalité réservée aux REST API v1, pas aux HTTP API v2 qu'on utilise ici).
"""

import json
import os

from agents import create_agent


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if headers.get("x-api-key") != os.environ["API_KEY"]:
        return {"statusCode": 401, "body": json.dumps({"error": "unauthorized"})}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "invalid JSON body"})}

    message = body.get("message")
    if not message:
        return {"statusCode": 400, "body": json.dumps({"error": "message is required"})}

    # Une instance neuve par requête : chaque appel HTTP est une conversation
    # indépendante, pas de fuite de contexte entre deux clients différents.
    agent = create_agent()
    result = agent(message)

    return {"statusCode": 200, "body": json.dumps({"response": str(result)})}
