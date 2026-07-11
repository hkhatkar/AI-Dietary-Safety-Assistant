#!/usr/bin/env node
/** CDK app entry point: instantiates the single stack that deploys the whole project. */
import * as path from 'node:path';
import * as dotenv from 'dotenv';
import * as cdk from 'aws-cdk-lib/core';
import { InfraStack } from '../lib/infra-stack';

dotenv.config({ path: path.join(__dirname, '../../.env') });

const app = new cdk.App();
new InfraStack(app, 'CanIEatThisStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.AWS_REGION ?? process.env.CDK_DEFAULT_REGION,
  },
});
