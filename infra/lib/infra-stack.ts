import * as path from 'node:path';
import * as fs from 'node:fs';
import { execSync } from 'node:child_process';
import * as cdk from 'aws-cdk-lib/core';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as cr from 'aws-cdk-lib/custom-resources';
import * as aoss from 'aws-cdk-lib/aws-opensearchserverless';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwIntegrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Construct } from 'constructs';

const REPO_ROOT = path.join(__dirname, '../../');
const BACKEND_DIR = path.join(REPO_ROOT, 'backend');
const FRONTEND_DIR = path.join(REPO_ROOT, 'frontend');
// Use the backend's own venv pip rather than whatever "pip3" resolves to on PATH -
// this machine's ambient pip3 turned out to be a broken old system Python 3.9 install.
const PIP = path.join(BACKEND_DIR, '.venv/bin/pip');

/**
 * The single CDK stack that deploys this whole project: the DynamoDB table (both menu
 * datasets), the Lambda backend behind an API Gateway HTTP API, the OpenSearch Serverless
 * collection for semantic notes search, and the S3+CloudFront-hosted frontend.
 */
export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // --- Structured menu data: DynamoDB ---
    const dishesTable = new dynamodb.Table(this, 'DishesTable', {
      tableName: 'can-i-eat-this-dishes',
      partitionKey: { name: 'id', type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    type Dish = { name: string; allergen_notes_raw: string | null; kcal_raw: string | null; price_gbp: number };
    const readMenu = (file: string): Dish[] =>
      JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'data', file), 'utf-8'));

    // Two datasets share one table, distinguished by a "dataset" attribute - "messy" is the
    // original brief's deliberately incomplete/ambiguous menu, "clean" is a complete,
    // unambiguous 50-dish menu for demonstrating the same pipeline on good-quality data.
    // Filtering by dataset happens in Python (app/db.py) after the LLM's generated query
    // runs, not by teaching the SQL-generation prompt about this attribute - simpler and
    // correct regardless of what the generated query's WHERE clause does or doesn't include.
    const messyMenu = readMenu('starter_menu.json').map((dish) => ({ ...dish, dataset: 'messy' }));
    const cleanMenu = readMenu('clean_menu.json').map((dish) => ({ ...dish, dataset: 'clean' }));
    const allDishes = [...messyMenu, ...cleanMenu];

    const putRequests = allDishes.map((dish, i) => ({
      PutRequest: {
        Item: {
          id: { N: String(i + 1) },
          name: { S: dish.name },
          // PartiQL's contains() has no case-insensitive/LOWER() equivalent, so a lowercase
          // shadow field is what generated queries actually match against.
          name_lower: { S: dish.name.toLowerCase() },
          allergen_notes_raw: { S: dish.allergen_notes_raw ?? '' },
          kcal_raw: { S: dish.kcal_raw ?? '' },
          price_gbp: { N: String(dish.price_gbp) },
          dataset: { S: dish.dataset },
        },
      },
    }));

    // DynamoDB's batchWriteItem caps out at 25 items per call, so 60 dishes need multiple
    // batches - one AwsCustomResource per chunk, each seeding its own slice of the table.
    const BATCH_SIZE = 25;
    const seedResources: cr.AwsCustomResource[] = [];
    for (let i = 0; i < putRequests.length; i += BATCH_SIZE) {
      const chunk = putRequests.slice(i, i + BATCH_SIZE);
      const id = `SeedDishesTable${i / BATCH_SIZE}`;
      const call: cr.AwsSdkCall = {
        service: 'DynamoDB',
        action: 'batchWriteItem',
        parameters: { RequestItems: { [dishesTable.tableName]: chunk } },
        physicalResourceId: cr.PhysicalResourceId.of(id),
      };
      const seed = new cr.AwsCustomResource(this, id, {
        onCreate: call,
        onUpdate: call,
        policy: cr.AwsCustomResourcePolicy.fromSdkCalls({ resources: [dishesTable.tableArn] }),
      });
      seed.node.addDependency(dishesTable);
      seedResources.push(seed);
    }

    const apiFunction = new lambda.Function(this, 'ApiFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: 'app.lambda_handler.handler',
      code: lambda.Code.fromAsset(BACKEND_DIR, {
        bundling: {
          // Dependencies here are all lightweight, widely-wheeled packages (no torch/ML
          // libs), so pip can just download prebuilt Linux wheels directly - no need to
          // spin up Docker to build/bundle them.
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          local: {
            tryBundle(outputDir: string): boolean {
              execSync(
                `"${PIP}" install -r requirements-lambda.txt ` +
                  `--platform manylinux2014_x86_64 --implementation cp --python-version 3.12 ` +
                  `--only-binary=:all: --target "${outputDir}"`,
                { cwd: BACKEND_DIR, stdio: 'inherit' },
              );
              execSync(`cp -r "${path.join(BACKEND_DIR, 'app')}" "${outputDir}/app"`);
              execSync(`cp -r "${path.join(REPO_ROOT, 'data')}" "${outputDir}/data"`);
              return true;
            },
          },
        },
      }),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      environment: {
        // AWS_REGION is set automatically by the Lambda runtime - don't set it here,
        // CloudFormation rejects it as a reserved environment variable name.
        ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY ?? '',
        ANTHROPIC_MODEL: process.env.ANTHROPIC_MODEL ?? 'claude-haiku-4-5-20251001',
        BEDROCK_EMBED_MODEL_ID: process.env.BEDROCK_EMBED_MODEL_ID ?? 'amazon.titan-embed-text-v2:0',
        DATA_DIR: '/var/task/data',
        DYNAMODB_TABLE_NAME: dishesTable.tableName,
        OPENSEARCH_INDEX: 'kitchen-notes',
      },
    });
    seedResources.forEach((seed) => apiFunction.node.addDependency(seed));

    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel'],
        resources: ['*'],
      }),
    );

    dishesTable.grantReadData(apiFunction);
    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['dynamodb:PartiQLSelect'],
        resources: [dishesTable.tableArn],
      }),
    );

    // --- Semantic notes data: OpenSearch Serverless (vector search) ---
    // Note: unlike everything else in this stack, an OpenSearch Serverless collection has a
    // real minimum cost floor from the moment it's created, even completely idle - deploy it
    // right before you need it and `cdk destroy` promptly afterward, don't leave it running.
    const notesCollectionName = 'can-i-eat-this-notes';

    const notesEncryptionPolicy = new aoss.CfnSecurityPolicy(this, 'NotesEncryptionPolicy', {
      name: `${notesCollectionName}-enc`,
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: [`collection/${notesCollectionName}`] }],
        AWSOwnedKey: true,
      }),
    });

    const notesNetworkPolicy = new aoss.CfnSecurityPolicy(this, 'NotesNetworkPolicy', {
      name: `${notesCollectionName}-net`,
      type: 'network',
      policy: JSON.stringify([
        {
          Rules: [
            { ResourceType: 'collection', Resource: [`collection/${notesCollectionName}`] },
            { ResourceType: 'dashboard', Resource: [`collection/${notesCollectionName}`] },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    const notesCollection = new aoss.CfnCollection(this, 'NotesCollection', {
      name: notesCollectionName,
      type: 'VECTORSEARCH',
    });
    notesCollection.addDependency(notesEncryptionPolicy);
    notesCollection.addDependency(notesNetworkPolicy);

    const notesDataAccessPolicy = new aoss.CfnAccessPolicy(this, 'NotesDataAccessPolicy', {
      name: `${notesCollectionName}-access`,
      type: 'data',
      policy: JSON.stringify([
        {
          Rules: [
            { ResourceType: 'collection', Resource: [`collection/${notesCollectionName}`], Permission: ['aoss:*'] },
            { ResourceType: 'index', Resource: [`index/${notesCollectionName}/*`], Permission: ['aoss:*'] },
          ],
          Principal: [
            apiFunction.role!.roleArn,
            // The deploying IAM identity, so local dev (uvicorn) can query/seed the
            // collection too. Falls back to the account root principal (grants access to
            // any IAM identity in the account whose own permissions allow it) if
            // DEPLOYER_IAM_PRINCIPAL_ARN isn't set in .env - set it to your own IAM
            // user/role ARN for local dev access without granting the whole account.
            process.env.DEPLOYER_IAM_PRINCIPAL_ARN || `arn:aws:iam::${this.account}:root`,
            // CDK's bootstrap CloudFormation execution role - the CollectionIndex resource
            // below is provisioned by CloudFormation itself, which needs data-plane access
            // to create the index.
            `arn:aws:iam::${this.account}:role/cdk-hnb659fds-cfn-exec-role-${this.account}-${this.region}`,
          ],
        },
      ]),
    });
    notesDataAccessPolicy.addDependency(notesCollection);

    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['aoss:APIAccessAll'],
        resources: [notesCollection.attrArn],
      }),
    );

    // Note: OpenSearch Serverless access policies take a short time to propagate after
    // creation - creating this index resource in the very same deploy as a brand-new access
    // policy can fail with AccessDenied. Once the policy has been live for a minute or so
    // (true for any deploy after the first), this creates cleanly.
    const notesIndex = new aoss.CfnCollectionIndex(this, 'NotesIndex', {
      id: notesCollection.attrId,
      indexName: 'kitchen-notes',
      indexSchema: JSON.stringify({
        settings: { index: { knn: true } },
        mappings: {
          properties: {
            embedding: {
              type: 'knn_vector',
              dimension: 1024,
              method: { name: 'hnsw', engine: 'faiss' },
            },
            id: { type: 'keyword' },
            title: { type: 'text' },
            text: { type: 'text' },
          },
        },
      }),
    });
    notesIndex.addDependency(notesDataAccessPolicy);

    apiFunction.addEnvironment('OPENSEARCH_ENDPOINT', notesCollection.attrCollectionEndpoint);

    new cdk.CfnOutput(this, 'DishesTableName', { value: dishesTable.tableName });
    new cdk.CfnOutput(this, 'OpenSearchEndpoint', { value: notesCollection.attrCollectionEndpoint });

    // API Gateway, not a Function URL: now that embeddings run via Bedrock instead of a local
    // model, cold starts are fast enough (a few seconds) to fit inside API Gateway's 30s cap,
    // so there's no reason left to give up its throttling, request validation, and WAF/auth
    // attachability. See infra/README.md for why this project used a Function URL earlier.
    const httpApi = new apigwv2.HttpApi(this, 'Api', {
      apiName: 'can-i-eat-this-api',
      corsPreflight: {
        allowOrigins: ['*'],
        allowMethods: [apigwv2.CorsHttpMethod.ANY],
        allowHeaders: ['*'],
      },
      defaultIntegration: new apigwIntegrations.HttpLambdaIntegration('ApiIntegration', apiFunction),
    });

    new cdk.CfnOutput(this, 'ApiUrl', {
      value: httpApi.apiEndpoint,
      description: 'Set VITE_API_BASE_URL to this value (no trailing slash) to point the frontend at the deployed API',
    });

    // --- Frontend: S3 + CloudFront ---
    // Vite bakes VITE_API_BASE_URL into the static build at build time, but the API
    // Function URL above is only a CloudFormation token until deploy actually runs - it
    // can't be interpolated into a build step that happens during synth. Since the
    // Function URL is stable for as long as ApiFunction itself isn't replaced, this reads
    // the already-known URL from the repo-root .env instead (same value as the ApiUrl
    // output). If the backend is ever destroyed and recreated under a new URL, update
    // VITE_API_BASE_URL in .env and redeploy to rebuild the frontend against it.
    const siteBucket = new s3.Bucket(this, 'SiteBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    const distribution = new cloudfront.Distribution(this, 'SiteDistribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      },
      defaultRootObject: 'index.html',
      errorResponses: [
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: '/index.html' },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: '/index.html' },
      ],
    });

    new s3deploy.BucketDeployment(this, 'DeploySite', {
      sources: [
        s3deploy.Source.asset(FRONTEND_DIR, {
          // CDK normally hashes the source directory to decide whether to re-run bundling,
          // but VITE_API_BASE_URL is baked in from an env var, not from any file under
          // FRONTEND_DIR - so changing only .env wouldn't be seen as a change, and CDK would
          // silently reuse a stale build with the old URL baked in. Forcing a fresh hash
          // every synth means this always rebuilds; the build itself is fast (~10-20s) and
          // deploys here are infrequent, so there's no real cost to skipping the cache.
          assetHashType: cdk.AssetHashType.CUSTOM,
          assetHash: `${Date.now()}`,
          bundling: {
            image: lambda.Runtime.NODEJS_20_X.bundlingImage,
            local: {
              tryBundle(outputDir: string): boolean {
                const apiUrl = process.env.VITE_API_BASE_URL ?? '';
                execSync('npm install', { cwd: FRONTEND_DIR, stdio: 'inherit' });
                execSync('npm run build', {
                  cwd: FRONTEND_DIR,
                  stdio: 'inherit',
                  env: { ...process.env, VITE_API_BASE_URL: apiUrl },
                });
                execSync(`cp -r "${path.join(FRONTEND_DIR, 'dist')}/." "${outputDir}/"`);
                return true;
              },
            },
          },
        }),
      ],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    new cdk.CfnOutput(this, 'SiteUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Public URL for the frontend',
    });
  }
}
