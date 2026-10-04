"""Point d'entrée Lambda, derrière API Gateway (HTTP API).

Auth par header X-API-Key, même patron que pme-rag-chatbot et novasupply-inbox-ai :
vérification manuelle dans le handler plutôt qu'un Usage Plan API Gateway natif
(fonctionnalité réservée aux REST API v1, pas aux HTTP API v2 qu'on utilise ici).
"""

import json
import os
import time
import uuid

import boto3

from agents import create_agent, tools_called

TRACES_TABLE_NAME = "novasupply-agent-traces"
_dynamodb = boto3.resource("dynamodb", region_name="eu-west-3")


def _write_trace(request_id: str, message: str, agent, result, latency_ms: int) -> None:
    """Enregistre la décision de l'agent (Phase 3 : observabilité).

    Appelé après coup, jamais avant la réponse au client : une erreur d'écriture
    de trace ne doit pas faire échouer la vraie requête, donc on l'isole dans
    son propre try/except plutôt que de la laisser remonter.
    """
    try:
        _dynamodb.Table(TRACES_TABLE_NAME).put_item(
            Item={
                "request_id": request_id,
                "timestamp": int(time.time()),
                "message": message,
                "tools_called": tools_called(agent),
                "stop_reason": result.stop_reason,
                "latency_ms": latency_ms,
            }
        )
    except Exception:
        pass


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
    start = time.monotonic()
    result = agent(message)
    latency_ms = int((time.monotonic() - start) * 1000)

    request_id = str(uuid.uuid4())
    _write_trace(request_id, message, agent, result, latency_ms)

    return {
        "statusCode": 200,
        "body": json.dumps({"response": str(result), "request_id": request_id}),
    }
