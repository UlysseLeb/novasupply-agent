import os

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_bedrock as bedrock,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    aws_s3vectors as s3vectors,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

FULFILLMENTS_TABLE_NAME = "novasupply-agent-fulfillments"
BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
# Titan Embeddings v2, dimension par défaut 1024 : doit matcher la dimension
# déclarée sur l'index S3 Vectors ci-dessous, sinon Bedrock refuse l'ingestion.
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSION = 1024


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

        # --- Phase 2 : Knowledge Base Bedrock sur les documents de procédure ---

        # Les documents sources (texte brut, non vectorisé) : bucket S3 classique.
        kb_docs_bucket = s3.Bucket(
            self,
            "KbDocsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        s3_deployment.BucketDeployment(
            self,
            "KbDocsDeployment",
            sources=[s3_deployment.Source.asset("../knowledge-base")],
            destination_bucket=kb_docs_bucket,
        )

        # Les embeddings eux-mêmes : S3 Vectors plutôt qu'OpenSearch Serverless.
        # OpenSearch Serverless facture un minimum même à l'arrêt (~300-700$/mois) ;
        # S3 Vectors est pay-per-use, sans infra à gérer — point de vigilance coût
        # identifié dès la conception du projet, résolu ici.
        vector_bucket_name = "novasupply-agent-kb-vectors"
        vector_bucket = s3vectors.CfnVectorBucket(self, "KbVectorBucket", vector_bucket_name=vector_bucket_name)
        vector_index = s3vectors.CfnIndex(
            self,
            "KbVectorIndex",
            vector_bucket_name=vector_bucket_name,
            index_name="novasupply-agent-kb-index",
            data_type="float32",
            dimension=EMBEDDING_DIMENSION,
            distance_metric="cosine",
        )
        vector_index.add_dependency(vector_bucket)

        # Rôle que le service Bedrock Knowledge Base assume pour lire les docs,
        # appeler le modèle d'embedding, et écrire/lire les vecteurs — distinct
        # du rôle d'exécution de la Lambda, qui lui ne fait qu'interroger la KB.
        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        kb_docs_bucket.grant_read(kb_role)
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{self.region}::foundation-model/{EMBEDDING_MODEL_ID}"],
            )
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3vectors:*"],
                resources=[vector_bucket.attr_vector_bucket_arn, vector_index.attr_index_arn],
            )
        )

        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "PolicyKnowledgeBase",
            name="novasupply-agent-policy-kb",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{self.region}::foundation-model/{EMBEDDING_MODEL_ID}",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
                    index_name="novasupply-agent-kb-index",
                ),
            ),
        )
        knowledge_base.add_dependency(vector_index)
        # Dépendance explicite sur le rôle : role_arn crée une dépendance CloudFormation
        # sur la ressource Role elle-même, mais pas sur sa policy inline (ressource
        # séparée) — sans ça, Bedrock a tenté d'assumer le rôle avant que la policy
        # s3vectors:* soit attachée, d'où le 403 rencontré au premier essai.
        knowledge_base.node.add_dependency(kb_role)

        bedrock.CfnDataSource(
            self,
            "PolicyDataSource",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            name="novasupply-agent-policy-docs",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=kb_docs_bucket.bucket_arn,
                ),
            ),
        )

        self.knowledge_base_id = knowledge_base.attr_knowledge_base_id
        CfnOutput(self, "KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)

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
                "KNOWLEDGE_BASE_ID": knowledge_base.attr_knowledge_base_id,
            },
        )
        agent_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve"],
                resources=[knowledge_base.attr_knowledge_base_arn],
            )
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
