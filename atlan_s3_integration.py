#!/usr/bin/env python3
"""
Delta Arc Corp S3 Integration Script
Atlan CSA Challenge Solution

This script integrates S3 assets into Atlan's metadata platform and establishes
lineage between PostgreSQL → S3 → Snowflake for Delta Arc Corp's data pipeline.

Author: Arijit Roy (AR)
"""

import os
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from pyatlan import AtlanClient
from pyatlan.model.assets import S3Bucket, S3Object, Table, Connection
from pyatlan.model.lineage import LineageProcess
from pyatlan.model.query import IndexSearchRequest
from pyatlan.model.enums import AtlanConnectorType


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class S3AssetInfo:
    """Data class for S3 asset information"""
    bucket_name: str
    object_key: str
    size: int
    last_modified: str
    content_type: str


class AtlanS3Integrator:
    """Main class for S3 integration with Atlan platform"""

    def __init__(self, base_url: str, api_token: str, initials: str = "AR"):
        """
        Initialize the S3 integrator

        Args:
            base_url: Atlan instance URL
            api_token: API token for authentication
            initials: Candidate initials for unique naming
        """
        self.client = AtlanClient(base_url=base_url, api_token=api_token)
        self.initials = initials
        self.bucket_arn = f"arn:aws:s3:::atlan-tech-challenge-{initials.lower()}"

    def create_s3_connection(self) -> Connection:
        """Create or get S3 connection in Atlan"""
        try:
            # Search for existing S3 connection
            request = IndexSearchRequest()
            request.size = 10
            request.query = f"connectorType:S3"

            response = self.client.asset.search(request)

            if response.assets:
                logger.info(f"Found existing S3 connection: {response.assets[0].qualified_name}")
                return response.assets[0]

            # Create new S3 connection
            connection = Connection.creator(
                name=f"S3-DeltaArc-{self.initials}",
                connector_type=AtlanConnectorType.S3
            ).build()

            created_connection = self.client.asset.save(connection)
            logger.info(f"Created S3 connection: {created_connection.qualified_name}")
            return created_connection

        except Exception as e:
            logger.error(f"Error creating S3 connection: {e}")
            raise

    def register_s3_bucket(self, connection: Connection) -> S3Bucket:
        """Register S3 bucket as Atlan asset"""
        try:
            bucket = S3Bucket.creator(
                name="atlan-tech-challenge",
                connection_qualified_name=connection.qualified_name,
                aws_arn=self.bucket_arn
            ).build()

            # Add metadata
            bucket.description = "S3 bucket for Delta Arc Corp data pipeline - staging area for PostgreSQL exports"
            bucket.owner_users = ["delta-arc-data-team"]
            bucket.certificate_status = "VERIFIED"

            created_bucket = self.client.asset.save(bucket)
            logger.info(f"Registered S3 bucket: {created_bucket.qualified_name}")
            return created_bucket

        except Exception as e:
            logger.error(f"Error registering S3 bucket: {e}")
            raise

    def register_s3_objects(self, bucket: S3Bucket, objects_info: List[S3AssetInfo]) -> List[S3Object]:
        """Register S3 objects as Atlan assets"""
        s3_objects = []

        for obj_info in objects_info:
            try:
                s3_object = S3Object.creator(
                    name=obj_info.object_key.split('/')[-1],  # File name
                    connection_qualified_name=bucket.connection_qualified_name,
                    s3_bucket_qualified_name=bucket.qualified_name,
                    aws_arn=f"{self.bucket_arn}/{obj_info.object_key}"
                ).build()

                # Add metadata
                s3_object.description = f"Data file in Delta Arc Corp pipeline - {obj_info.content_type}"
                s3_object.size = obj_info.size
                s3_object.s3_object_content_type = obj_info.content_type

                # Infer table mapping from object key
                if 'users' in obj_info.object_key.lower():
                    s3_object.meanings = ["user-data", "pii-data"]
                elif 'transactions' in obj_info.object_key.lower():
                    s3_object.meanings = ["financial-data", "transactional"]
                elif 'accounts' in obj_info.object_key.lower():
                    s3_object.meanings = ["account-data", "financial"]

                created_object = self.client.asset.save(s3_object)
                s3_objects.append(created_object)
                logger.info(f"Registered S3 object: {created_object.qualified_name}")

            except Exception as e:
                logger.error(f"Error registering S3 object {obj_info.object_key}: {e}")
                continue

        return s3_objects

    def get_postgres_tables(self, initials: str) -> List[Table]:
        """Get PostgreSQL tables from Atlan"""
        try:
            request = IndexSearchRequest()
            request.size = 50
            request.query = f"__typename:Table AND connectorType:POSTGRES AND qualifiedName:*postgres-{initials.lower()}*"

            response = self.client.asset.search(request)
            logger.info(f"Found {len(response.assets)} PostgreSQL tables")
            return response.assets

        except Exception as e:
            logger.error(f"Error fetching PostgreSQL tables: {e}")
            return []

    def get_snowflake_tables(self, initials: str) -> List[Table]:
        """Get Snowflake tables from Atlan"""
        try:
            request = IndexSearchRequest()
            request.size = 50
            request.query = f"__typename:Table AND connectorType:SNOWFLAKE AND qualifiedName:*snowflake-{initials.lower()}*"

            response = self.client.asset.search(request)
            logger.info(f"Found {len(response.assets)} Snowflake tables")
            return response.assets

        except Exception as e:
            logger.error(f"Error fetching Snowflake tables: {e}")
            return []

    def create_lineage_postgres_to_s3(self, postgres_tables: List[Table], s3_objects: List[S3Object]):
        """Create lineage from PostgreSQL tables to S3 objects"""
        for pg_table in postgres_tables:
            # Find matching S3 object based on table name
            table_name = pg_table.name.lower()
            matching_s3_objects = [
                obj for obj in s3_objects
                if table_name in obj.name.lower() or table_name in obj.aws_arn.lower()
            ]

            for s3_obj in matching_s3_objects:
                try:
                    # Create lineage process
                    process = LineageProcess.creator(
                        name=f"PostgreSQL-to-S3-{table_name}",
                        connection_qualified_name=s3_obj.connection_qualified_name,
                        inputs=[pg_table],
                        outputs=[s3_obj]
                    ).build()

                    process.description = f"Data export from PostgreSQL {pg_table.name} to S3"

                    self.client.asset.save(process)
                    logger.info(f"Created lineage: {pg_table.qualified_name} → {s3_obj.qualified_name}")

                except Exception as e:
                    logger.error(f"Error creating PostgreSQL→S3 lineage: {e}")

    def create_lineage_s3_to_snowflake(self, s3_objects: List[S3Object], snowflake_tables: List[Table]):
        """Create lineage from S3 objects to Snowflake tables"""
        for sf_table in snowflake_tables:
            # Find matching S3 object based on table name
            table_name = sf_table.name.lower()
            matching_s3_objects = [
                obj for obj in s3_objects
                if table_name in obj.name.lower() or table_name in obj.aws_arn.lower()
            ]

            for s3_obj in matching_s3_objects:
                try:
                    # Create lineage process
                    process = LineageProcess.creator(
                        name=f"S3-to-Snowflake-{table_name}",
                        connection_qualified_name=sf_table.connection_qualified_name,
                        inputs=[s3_obj],
                        outputs=[sf_table]
                    ).build()

                    process.description = f"Data ingestion from S3 to Snowflake {sf_table.name}"

                    self.client.asset.save(process)
                    logger.info(f"Created lineage: {s3_obj.qualified_name} → {sf_table.qualified_name}")

                except Exception as e:
                    logger.error(f"Error creating S3→Snowflake lineage: {e}")

    def run_integration(self):
        """Main integration workflow"""
        logger.info("Starting Delta Arc Corp S3 integration...")

        try:
            # Step 1: Create S3 connection
            connection = self.create_s3_connection()

            # Step 2: Register S3 bucket
            bucket = self.register_s3_bucket(connection)

            # Step 3: Mock S3 objects data (in real scenario, this would come from S3 API)
            sample_objects = [
                S3AssetInfo(
                    bucket_name="atlan-tech-challenge",
                    object_key="exports/users/2024/01/users_20240115.parquet",
                    size=1024000,
                    last_modified="2024-01-15T10:30:00Z",
                    content_type="application/parquet"
                ),
                S3AssetInfo(
                    bucket_name="atlan-tech-challenge",
                    object_key="exports/transactions/2024/01/transactions_20240115.parquet",
                    size=5120000,
                    last_modified="2024-01-15T10:45:00Z",
                    content_type="application/parquet"
                ),
                S3AssetInfo(
                    bucket_name="atlan-tech-challenge",
                    object_key="exports/accounts/2024/01/accounts_20240115.parquet",
                    size=512000,
                    last_modified="2024-01-15T10:15:00Z",
                    content_type="application/parquet"
                )
            ]

            # Step 4: Register S3 objects
            s3_objects = self.register_s3_objects(bucket, sample_objects)

            # Step 5: Get existing PostgreSQL and Snowflake tables
            postgres_tables = self.get_postgres_tables(self.initials)
            snowflake_tables = self.get_snowflake_tables(self.initials)

            # Step 6: Create lineage relationships
            self.create_lineage_postgres_to_s3(postgres_tables, s3_objects)
            self.create_lineage_s3_to_snowflake(s3_objects, snowflake_tables)

            logger.info("✅ S3 integration completed successfully!")
            logger.info(f"📊 Registered: 1 S3 bucket, {len(s3_objects)} S3 objects")
            logger.info(f"🔗 Created lineage for {len(postgres_tables)} PostgreSQL → S3 → {len(snowflake_tables)} Snowflake")

        except Exception as e:
            logger.error(f"❌ Integration failed: {e}")
            raise


def main():
    """Main execution function"""
    # Configuration
    ATLAN_BASE_URL = os.getenv("ATLAN_BASE_URL", "https://tech-challenge.atlan.com")
    ATLAN_API_TOKEN = os.getenv("ATLAN_API_TOKEN")
    CANDIDATE_INITIALS = "ARY"  # Arijit Roy initials

    if not ATLAN_API_TOKEN:
        logger.error("ATLAN_API_TOKEN environment variable is required")
        return

    # Run integration
    integrator = AtlanS3Integrator(
        base_url=ATLAN_BASE_URL,
        api_token=ATLAN_API_TOKEN,
        initials=CANDIDATE_INITIALS
    )

    integrator.run_integration()


if __name__ == "__main__":
    main()
