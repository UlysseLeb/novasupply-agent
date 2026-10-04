import os

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

FULFILLMENTS_TABLE_NAME = "novasupply-agent-fulfillments"
BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


class NovaSupplyAgentStack(Stack):
    """Phase 1 : agent packagé en Lambda derrière API Gateway (HTTP API).

    Une seule stack pour l'instant (DynamoDB + Lambda + API Gateway) : pas
    besoin de la découper davantage tant qu'on est sur un seul environnement
    de prototype, on splittera si un vrai besoin de déploiement multi-env apparaît.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Donnée simulée d'expédition (NovaSupply n'a pas de vrai système d'entrepôt) :
        # seule donnée qui n'existe nulle part ailleurs, pas de duplication de HubSpot.
        fulfillments_table = dynamodb.Table(
            self,
            "FulfillmentsTable",
            table_name=FULFILLMENTS_TABLE_NAME,
            partition_key=dynamodb.Attribute(name="order_ref", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            # DESTROY plutôt que RETAIN : prototype d'apprentissage, pas de donnée
            # réelle à protéger si on détruit et recrée la stack.
            removal_policy=RemovalPolicy.DESTROY,
        )

        agent_function = PythonFunction(
            self,
            "AgentFunction",
            entry="../src",
            index="lambda_handler.py",
            handler="handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(60),  # un appel agent enchaîne plusieurs tours de modèle + outils
            memory_size=512,
            environment={
                "API_KEY": os.environ["NOVASUPPLY_API_KEY"],
                "HUBSPOT_PRIVATE_APP_TOKEN": os.environ["HUBSPOT_PRIVATE_APP_TOKEN"],
            },
        )

        fulfillments_table.grant_read_data(agent_function)

        # Scope volontairement large sur Bedrock (apprentissage) plutôt qu'un ARN
        # précis de profil d'inférence : à resserrer si ce projet passe en prod réelle.
        agent_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["*"],
            )
        )

        http_api = apigwv2.HttpApi(
            self,
            "AgentApi",
            default_integration=apigwv2_integrations.HttpLambdaIntegration("AgentIntegration", agent_function),
        )

        self.api_url = http_api.url
        CfnOutput(self, "ApiUrl", value=http_api.url or "")
