#!/usr/bin/env bash
# Provision the shared Oracle 19c source on Amazon RDS (Standard Edition Two, license included,
# non-CDB, single AZ, publicly reachable from the listed CIDRs). Requires the AWS CLI with
# credentials for the target account. Review every value before running; this creates billable
# resources. Tear down with: aws rds delete-db-instance --db-instance-identifier "$NAME" --skip-final-snapshot
set -euo pipefail

NAME=${NAME:-product-benchmark-oracle}
REGION=${REGION:-us-east-1}
CLASS=${CLASS:-db.m5.large}          # db.t3.large is enough for Tier A; Tier B needs m5.large or larger
STORAGE_GB=${STORAGE_GB:-100}
ENGINE_VERSION=${ENGINE_VERSION:-19}  # resolves to the latest 19.0.0.0.ru-* for oracle-se2
MASTER_USER=${MASTER_USER:-admin}
MASTER_PASSWORD=${MASTER_PASSWORD:?set MASTER_PASSWORD}
ALLOW_CIDRS=${ALLOW_CIDRS:?comma-separated CIDRs allowed to reach port 1521 (benchmark host, Confluent, Tapstate, Fivetran egress)}
VPC_ID=${VPC_ID:-$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)}

PG="$NAME-pg"
aws rds create-db-parameter-group --region "$REGION" --db-parameter-group-name "$PG" \
  --db-parameter-group-family oracle-se2-19 --description "product-benchmark: goldengate replication on" >/dev/null
aws rds modify-db-parameter-group --region "$REGION" --db-parameter-group-name "$PG" \
  --parameters "ParameterName=enable_goldengate_replication,ParameterValue=TRUE,ApplyMethod=immediate" >/dev/null

SG=$(aws ec2 create-security-group --region "$REGION" --group-name "$NAME-sg" --vpc-id "$VPC_ID" \
  --description "product-benchmark oracle 1521" --query GroupId --output text)
IFS=, read -ra CIDRS <<<"$ALLOW_CIDRS"
for c in "${CIDRS[@]}"; do
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG" --protocol tcp --port 1521 --cidr "$c" >/dev/null
done

aws rds create-db-instance --region "$REGION" --db-instance-identifier "$NAME" \
  --engine oracle-se2 --engine-version "$ENGINE_VERSION" --license-model license-included \
  --db-instance-class "$CLASS" --allocated-storage "$STORAGE_GB" --storage-type gp3 \
  --db-name ORCL --master-username "$MASTER_USER" --master-user-password "$MASTER_PASSWORD" \
  --backup-retention-period 1 --no-multi-az --publicly-accessible \
  --vpc-security-group-ids "$SG" --db-parameter-group-name "$PG" \
  --character-set-name AL32UTF8 --tags Key=purpose,Value=product-benchmark >/dev/null

echo "creating $NAME in $REGION; wait with: aws rds wait db-instance-available --region $REGION --db-instance-identifier $NAME"
echo "endpoint: aws rds describe-db-instances --region $REGION --db-instance-identifier $NAME --query 'DBInstances[0].Endpoint.Address' --output text"
