#!/usr/bin/env python3
import os
import secrets

import aws_cdk as cdk

from infra.infra_stack import NovaSupplyAgentStack

# Charge .env à la racine du projet (même mécanisme que src/run_tests.py) :
# le token HubSpot et la clé API de l'agent ne doivent jamais être écrits en dur ici.
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
_env_lines = []
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        _env_lines = f.readlines()
    for line in _env_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key, value)

# La clé API de l'agent (différente du token HubSpot) : générée une fois,
# puis réutilisée à chaque déploiement pour que l'URL reste appelable avec
# la même clé sans la régénérer à chaque `cdk deploy`.
if not os.environ.get("NOVASUPPLY_API_KEY"):
    new_key = secrets.token_urlsafe(32)
    os.environ["NOVASUPPLY_API_KEY"] = new_key
    with open(_ENV_PATH, "a") as f:
        f.write(f"\nNOVASUPPLY_API_KEY={new_key}\n")
    print(f"NOVASUPPLY_API_KEY générée et ajoutée à .env : {_ENV_PATH}")

app = cdk.App()
NovaSupplyAgentStack(
    app,
    "NovaSupplyAgentStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region="eu-west-3",
    ),
)

app.synth()
