from pyatlan.client.atlan import AtlanClient
import os
import json
import logging
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv
from botocore import UNSIGNED
from botocore.client import Config

from pyatlan.model.assets import Connection, S3Bucket, S3Object, Table, Process, Asset, Column
from pyatlan.model.enums import AtlanConnectorType
from pyatlan.model.fluent_search import FluentSearch

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration constants from environment variables
CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS"))
POSTGRES_CACHE_FILE = os.getenv("POSTGRES_CACHE_FILE")
SNOWFLAKE_CACHE_FILE = os.getenv("SNOWFLAKE_CACHE_FILE")

# Atlan Tenant configuration
ATLAN_BASE_URL = os.getenv("ATLAN_BASE_URL")
ATLAN_API_TOKEN = os.getenv("ATLAN_API_TOKEN")

# S3 configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_BUCKET_ARN = os.getenv("S3_BUCKET_ARN")
S3_CONNECTION_NAME = os.getenv("S3_CONNECTION_NAME")
S3_PREFIX = os.getenv("S3_PREFIX")

# Database connections
POSTGRES_CONNECTION_NAME = os.getenv("POSTGRES_CONNECTION_NAME")
SNOWFLAKE_CONNECTION_NAME = os.getenv("SNOWFLAKE_CONNECTION_NAME")

client = AtlanClient(
    base_url=ATLAN_BASE_URL,
    api_key=ATLAN_API_TOKEN
)


def clear_all_cache():
    """
    Clear all cache files
    """
    cache_files = [POSTGRES_CACHE_FILE, SNOWFLAKE_CACHE_FILE]
    for cache_file in cache_files:
        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logger.info(f"🗑️ Cleared cache file: {cache_file}")
            else:
                logger.info(f"📁 Cache file not found: {cache_file}")
        except Exception as e:
            logger.error(f"❌ Error clearing cache file {cache_file}: {e}")


def get_cache_status():
    """
    Get status of all cache files
    """
    cache_files = [
        ("PostgreSQL", POSTGRES_CACHE_FILE),
        ("Snowflake", SNOWFLAKE_CACHE_FILE)
    ]

    for name, cache_file in cache_files:
        if os.path.exists(cache_file):
            cache_data = load_cache_from_file(cache_file)
            if cache_data and 'timestamp' in cache_data:
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                age = datetime.now() - cache_time
                is_valid = is_cache_valid(cache_file)
                status = "✅ Valid" if is_valid else "⏰ Expired"
                logger.info(f"{name} cache: {status} (age: {age}, items: {len(cache_data.get('data', []))})")
            else:
                logger.info(f"{name} cache: ❌ Invalid format")
        else:
            logger.info(f"{name} cache: 📁 Not found")


def list_s3_bucket_objects(bucket_name: str = S3_BUCKET_NAME) -> List[str]:
    """
    List objects in a public S3 bucket and return their keys
    """
    try:
        # Create S3 client for public bucket access
        s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

        # List objects in the specified bucket
        response = s3.list_objects_v2(Bucket=bucket_name)
        objects = response.get('Contents', [])
        logger.info(f"📦 Found {len(objects)} objects in S3 bucket '{bucket_name}':")

        object_keys = []
        for obj in objects:
            logger.info(f"  📄 {obj['Key']} (Size: {obj['Size']} bytes, Modified: {obj['LastModified']})")
            object_keys.append(obj['Key'])

        return object_keys

    except Exception as e:
        logger.error(f"❌ Error listing S3 objects: {e}")
        return []


def integration_with_S3(bucket_name: str = S3_BUCKET_NAME, bucket_arn: str = S3_BUCKET_ARN, prefix: str = S3_PREFIX):
    """
    Complete S3 integration workflow: setup connection, register bucket, and create objects
    """
    logger.info("🚀 Starting S3 integration workflow...")

    # ------------- setup s3 connection ---------------
    logger.info("🔍 Setting up S3 connection...")

    # Check if connection already exists
    existing_connection_qn = get_connection_qualified_name(
        connection_name=S3_CONNECTION_NAME,
        connection_type=AtlanConnectorType.S3
    )

    if existing_connection_qn:
        logger.info(f"✅ S3 connection already exists: {existing_connection_qn}")
        connection_qualified_name = existing_connection_qn
    else:
        logger.info("🔧 Creating new S3 connection...")
        try:
            connection = Connection.creator(
                client=client,
                name=S3_CONNECTION_NAME,
                connector_type=AtlanConnectorType.S3,
                admin_users=["arijitroy003"],
            )
            response = client.asset.save(connection)
            connection_qualified_name = response.assets_created(asset_type=Connection)[0].qualified_name
            logger.info(f"✅ S3 connection created successfully: {connection_qualified_name}")
        except Exception as e:
            logger.error(f"❌ Error creating S3 connection: {e}")
            return None

    # ------------- register s3 bucket ---------------
    logger.info("🔍 Checking if S3 bucket already exists...")

    search_request = (
        FluentSearch()
        .where(Asset.TYPE_NAME.eq("S3Bucket"))
        .where(S3Bucket.AWS_ARN.eq(bucket_arn))
        .include_on_results(Asset.QUALIFIED_NAME)
        .include_on_results(Asset.NAME)
        .page_size(1)
    ).to_request()

    search_response = client.asset.search(search_request)
    existing_buckets = list(search_response)

    if existing_buckets:
        bucket_qualified_name = existing_buckets[0].qualified_name
        logger.info(f"✅ S3 bucket already exists: {bucket_qualified_name}")
    else:
        logger.info("🔧 Creating new S3 bucket...")
        s3bucket = S3Bucket.creator(
            name=f"{bucket_name}-ary-test",
            connection_qualified_name=connection_qualified_name,
            aws_arn=bucket_arn
        )
        s3bucket.s3_object_count = 8  # Based on the 8 CSV files we found
        response = client.asset.save(s3bucket)
        bucket_qualified_name = response.assets_created(asset_type=S3Bucket)[0].qualified_name
        logger.info(f"✅ S3 bucket created successfully: {bucket_qualified_name}")

    # ------------- register s3 objects with ary prefix ---------------
    logger.info("🔍 Getting list of files from S3 bucket...")

    # Get actual files from S3 bucket using boto3
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    response = s3.list_objects_v2(Bucket=bucket_name)
    s3_filenames = [obj['Key'] for obj in response.get('Contents', [])]
    logger.info(f"📦 Found {len(s3_filenames)} files in S3 bucket: {s3_filenames}")

    # Check if S3 objects with prefix already exist in Atlan
    logger.info("🔍 Checking if S3 objects with prefix already exist in Atlan...")
    search_request = (
        FluentSearch()
        .where(Asset.TYPE_NAME.eq("S3Object"))
        .where(S3Object.S3BUCKET_QUALIFIED_NAME.eq(bucket_qualified_name))
        .include_on_results(Asset.QUALIFIED_NAME)
        .include_on_results(Asset.NAME)
        .page_size(50)
    ).to_request()

    search_response = client.asset.search(search_request)
    existing_objects = list(search_response)
    existing_object_names = [obj.name for obj in existing_objects]

    logger.info(f"📋 Found {len(existing_objects)} existing S3 objects in Atlan: {existing_object_names}")

    # Create S3 objects with prefix directly (optimized workflow)
    created_s3_objects = []

    for file_name in s3_filenames:
        try:
            # Create S3 object with prefix directly
            s3object = S3Object.creator_with_prefix(
                name=file_name,
                connection_qualified_name=connection_qualified_name,
                prefix=prefix,
                s3_bucket_name=bucket_name,
                s3_bucket_qualified_name=bucket_qualified_name,
            )
            response = client.asset.save(s3object)

            # Extract object from response
            created_objects = response.assets_created(asset_type=S3Object)
            updated_objects = response.assets_updated(asset_type=S3Object)

            if created_objects:
                created_object = created_objects[0]
                logger.info(f"✅ Created S3 object: {file_name}")
                logger.info(f"--📋 Qualified Name: {created_object.qualified_name}")
                created_s3_objects.append(created_object)
            elif updated_objects:
                updated_object = updated_objects[0]
                logger.info(f"🔄 Updated S3 object: {file_name}")
                logger.info(f"--📋 Qualified Name: {updated_object.qualified_name}")
                created_s3_objects.append(updated_object)
            else:
                logger.info(f"✅ Processed S3 object: {file_name}")

        except Exception as e:
            logger.error(f"❌ Error creating S3 object {file_name}: {e}")

    logger.info("✅ S3 integration workflow completed successfully!")
    return {
        "connection_qualified_name": connection_qualified_name,
        "bucket_qualified_name": bucket_qualified_name,
        "s3_objects": created_s3_objects,
        "object_count": len(created_s3_objects)
    }



def load_cache_from_file(filename: str) -> Optional[Dict]:
    """
    Load cached data from JSON file
    """
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                cache_data = json.load(f)
                logger.info(f"📁 Loaded cache from {filename}")
                return cache_data
        else:
            logger.info(f"📁 No cache file found: {filename}")
            return None
    except Exception as e:
        logger.warning(f"⚠️ Error loading cache from {filename}: {e}")
        return None


def save_cache_to_file(data: List, filename: str) -> bool:
    """
    Save data to JSON file with timestamp
    """
    try:
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        with open(filename, 'w') as f:
            json.dump(cache_data, f, indent=2)
        logger.info(f"💾 Saved cache to {filename} with {len(data)} items")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving cache to {filename}: {e}")
        return False


def is_cache_valid(filename: str, max_age_hours: int = CACHE_EXPIRY_HOURS) -> bool:
    """
    Check if cache file exists and is within the expiry time
    """
    try:
        if not os.path.exists(filename):
            return False

        cache_data = load_cache_from_file(filename)
        if not cache_data or 'timestamp' not in cache_data:
            return False

        cache_time = datetime.fromisoformat(cache_data['timestamp'])
        expiry_time = cache_time + timedelta(hours=max_age_hours)

        is_valid = datetime.now() < expiry_time
        if is_valid:
            logger.info(f"✅ Cache {filename} is valid (age: {datetime.now() - cache_time})")
        else:
            logger.info(f"⏰ Cache {filename} expired (age: {datetime.now() - cache_time})")

        return is_valid
    except Exception as e:
        logger.warning(f"⚠️ Error checking cache validity for {filename}: {e}")
        return False


def get_connection_qualified_name(connection_name: str, connection_type: AtlanConnectorType) -> Optional[str]:
    """
    Get the qualified name of a connection
    """
    try:
        connections = client.asset.find_connections_by_name(
            name=connection_name,
            connector_type=connection_type,
            attributes=[]
        )
        if connections and len(connections) > 0:
            return connections[0].qualified_name
        else:
            logger.warning(f"No connection found with name: {connection_name}")
            return None
    except Exception as e:
        logger.error(f"Error finding connection {connection_name}: {e}")
        return None
    

def find_postgres_assets(force_refresh: bool = False) -> List[List[str]]:
    """
    Find all PostgreSQL assets (tables, columns, schemas) for postgres-ary connection

    Args:
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        List of assets as [qualified_name, name, type_name] tuples
    """
    # Check cache first unless force refresh is requested
    if not force_refresh and is_cache_valid(POSTGRES_CACHE_FILE):
        cache_data = load_cache_from_file(POSTGRES_CACHE_FILE)
        if cache_data and 'data' in cache_data:
            logger.info(f"📊 Using cached PostgreSQL tables ({len(cache_data['data'])} items)")
            return cache_data['data']

    logger.info("📊 Fetching PostgreSQL assets from API...")
    postgres_ary_qualified_name = get_connection_qualified_name(
            connection_name=POSTGRES_CONNECTION_NAME,
            connection_type=AtlanConnectorType.POSTGRES,
    )
    logger.info(f"📊 Found postgres-ary connection: {postgres_ary_qualified_name}")

    postgres_assets = []

    if postgres_ary_qualified_name:
        try:
            # Search for all assets and filter by qualified name prefix
            search_request = (
                FluentSearch()
                .where(Asset.QUALIFIED_NAME.startswith(postgres_ary_qualified_name))
                .include_on_results(Asset.QUALIFIED_NAME)
                .include_on_results(Asset.NAME)
                .include_on_results(Asset.TYPE_NAME)
            ).to_request()
            

            response = client.asset.search(search_request)

            # Iterate through all pages of results
            logger.info("📊 Iterating through all pages of PostgreSQL assets results...")
            total_processed = 0

            for asset in response:  # This iterates through all pages automatically
                total_processed += 1

                # Filter for assets that belong to postgres-ary connection
                if (asset.qualified_name and
                    asset.qualified_name.startswith(f"{postgres_ary_qualified_name}/")):
                    postgres_assets.append([asset.qualified_name, asset.name, asset.type_name])

                # Log progress every 100 assets
                if total_processed % 100 == 0:
                    logger.info(f"📊 Processed {total_processed} assets, found {len(postgres_assets)} PostgreSQL assets so far...")

            logger.info(f"📊 Completed search: processed {total_processed} total assets")
            logger.info(f"📊 Found {len(postgres_assets)} tables in postgres-ary connection:")
            for asset in postgres_assets:
                logger.info(f"  🔹 {asset[1]} (Type: {asset[2]}, Qualified Name: {asset[0]})")

            # Save to cache
            save_cache_to_file(postgres_assets, POSTGRES_CACHE_FILE)

        except Exception as e:
            logger.error(f"❌ Error searching postgres-ary assets: {e}")

    return postgres_assets


def find_snowflake_assets(force_refresh: bool = False) -> List[List[str]]:
    """
    Find all Snowflake assets (tables, columns, schemas) for snowflake-ary connection

    Args:
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        List of assets as [qualified_name, name, type_name] tuples
    """
    # Check cache first unless force refresh is requested
    if not force_refresh and is_cache_valid(SNOWFLAKE_CACHE_FILE):
        cache_data = load_cache_from_file(SNOWFLAKE_CACHE_FILE)
        if cache_data and 'data' in cache_data:
            logger.info(f"❄️ Using cached Snowflake assets ({len(cache_data['data'])} items)")
            return cache_data['data']

    logger.info("❄️ Fetching Snowflake assets from API...")
    snowflake_ary_qualified_name = get_connection_qualified_name(
            connection_name=SNOWFLAKE_CONNECTION_NAME,
            connection_type=AtlanConnectorType.SNOWFLAKE,
        )
    logger.info(f"❄️ Found snowflake-ary connection: {snowflake_ary_qualified_name}")

    snowflake_assets = []

    if snowflake_ary_qualified_name:
        try:
            # Search for all assets and filter by qualified name prefix
            search_request = (
                FluentSearch()
                .where(Asset.QUALIFIED_NAME.startswith(snowflake_ary_qualified_name))
                .include_on_results(Asset.QUALIFIED_NAME)
                .include_on_results(Asset.NAME)
                .include_on_results(Asset.TYPE_NAME)
            ).to_request()

            response = client.asset.search(search_request)

            # Iterate through all pages of results
            logger.info("❄️ Iterating through all pages of Snowflake assets results...")
            total_processed = 0

            for asset in response:  # This iterates through all pages automatically
                total_processed += 1

                # Filter for assets that belong to snowflake-ary connection
                if (asset.qualified_name and
                    asset.qualified_name.startswith(f"{snowflake_ary_qualified_name}/")):
                    snowflake_assets.append([asset.qualified_name, asset.name, asset.type_name])

                # Log progress every 100 assets
                if total_processed % 100 == 0:
                    logger.info(f"❄️ Processed {total_processed} assets, found {len(snowflake_assets)} Snowflake assets so far...")

            logger.info(f"❄️ Completed search: processed {total_processed} total assets")
            logger.info(f"❄️ Found {len(snowflake_assets)} assets in snowflake-ary connection:")
            for asset in snowflake_assets:
                logger.info(f"  🔹 {asset[1]} (Type: {asset[2]}, Qualified Name: {asset[0]})")

            # Save to cache
            save_cache_to_file(snowflake_assets, SNOWFLAKE_CACHE_FILE)

        except Exception as e:
            logger.error(f"❌ Error searching snowflake-ary assets: {e}")

    return snowflake_assets

def create_table_lineage(postgres_assets: List[List[str]], s3_objects: List[S3Object], snowflake_assets: List[List[str]]):
    """
    Create table-level lineage processes: PostgreSQL tables → S3 objects → Snowflake tables

    Args:
        postgres_assets: List of PostgreSQL assets from find_postgres_assets()
        s3_objects: List of S3Object instances from integration_with_S3()
        snowflake_assets: List of Snowflake assets from find_snowflake_assets()
    """
    logger.info("🔗 Starting table-level lineage creation...")

    # Filter to get only tables from postgres and snowflake assets
    postgres_tables = [asset for asset in postgres_assets if len(asset) >= 3 and asset[2] == 'Table']
    snowflake_tables = [asset for asset in snowflake_assets if len(asset) >= 3 and asset[2] == 'Table']

    logger.info(f"📊 Found {len(postgres_tables)} PostgreSQL tables")
    logger.info(f"📦 Found {len(s3_objects)} S3 objects")
    logger.info(f"❄️ Found {len(snowflake_tables)} Snowflake tables")

    # Create lineage for each matching set of assets
    lineage_count = 0
    for postgres_table in postgres_tables:
        postgres_table_name = postgres_table[1].upper()  # Table name
        postgres_qualified_name = postgres_table[0]      # Qualified name

        # Find matching S3 object by name
        matching_s3_objects = [
            s3_obj for s3_obj in s3_objects
            if s3_obj.name.upper().replace('.CSV', '') == postgres_table_name
        ]

        # Find matching Snowflake table by name
        matching_snowflake_tables = [
            sf_table for sf_table in snowflake_tables
            if sf_table[1].upper() == postgres_table_name
        ]

        if matching_s3_objects and matching_snowflake_tables:
            s3_object = matching_s3_objects[0]
            snowflake_table = matching_snowflake_tables[0]
            snowflake_qualified_name = snowflake_table[0]

            try:
                # Create PostgreSQL → S3 → Snowflake lineage process
                process = Process.creator(
                    name=f"ETL Pipeline: {postgres_table_name}",
                    connection_qualified_name=s3_object.connection_qualified_name,
                    process_id=f"etl_pipeline_{postgres_table_name.lower()}",
                    inputs=[
                        Table.ref_by_qualified_name(qualified_name=postgres_qualified_name)
                    ],
                    outputs=[
                        Table.ref_by_qualified_name(qualified_name=snowflake_qualified_name)
                    ]
                )

                # Add process metadata
                process.description = f"ETL pipeline: PostgreSQL {postgres_table_name} → S3 → Snowflake {postgres_table_name}"
                process.sql = f"-- ETL process for {postgres_table_name}\n-- Extract from PostgreSQL, Load to S3, Transform and Load to Snowflake"
                process.source_url = "https://atlan-tech-challenge.s3.amazonaws.com"

                # Save the process
                client.asset.save(process)
                logger.info(f"✅ Created table lineage process: {postgres_table_name}")
                logger.info(f"   📊 PostgreSQL: {postgres_qualified_name}")
                logger.info(f"   📦 S3: {s3_object.qualified_name}")
                logger.info(f"   ❄️ Snowflake: {snowflake_qualified_name}")

                lineage_count += 1

            except Exception as e:
                logger.error(f"❌ Error creating table lineage for {postgres_table_name}: {e}")

    logger.info(f"🎉 Table lineage creation completed! Created {lineage_count} lineage processes.")


def create_column_lineage(postgres_assets: List[List[str]], snowflake_assets: List[List[str]]):
    """
    Create column-level lineage processes: PostgreSQL columns → Snowflake columns

    Args:
        postgres_assets: List of PostgreSQL assets from find_postgres_assets()
        snowflake_assets: List of Snowflake assets from find_snowflake_assets()
    """
    logger.info("🔗 Starting column-level lineage creation...")

    # Filter to get only columns from postgres and snowflake assets
    postgres_columns = [asset for asset in postgres_assets if len(asset) >= 3 and asset[2] == 'Column']
    snowflake_columns = [asset for asset in snowflake_assets if len(asset) >= 3 and asset[2] == 'Column']

    logger.info(f"📊 Found {len(postgres_columns)} PostgreSQL columns")
    logger.info(f"❄️ Found {len(snowflake_columns)} Snowflake columns")

    # Group columns by table name for easier matching
    postgres_cols_by_table = {}
    snowflake_cols_by_table = {}

    for col in postgres_columns:
        # Extract table name from qualified name (e.g., .../CUSTOMERS/CUSTOMERID -> CUSTOMERS)
        table_name = col[0].split('/')[-2].upper()
        column_name = col[1].upper()
        if table_name not in postgres_cols_by_table:
            postgres_cols_by_table[table_name] = []
        postgres_cols_by_table[table_name].append((column_name, col[0]))

    for col in snowflake_columns:
        # Extract table name from qualified name
        table_name = col[0].split('/')[-2].upper()
        column_name = col[1].upper()
        if table_name not in snowflake_cols_by_table:
            snowflake_cols_by_table[table_name] = []
        snowflake_cols_by_table[table_name].append((column_name, col[0]))

    # Create column lineage for matching tables
    column_lineage_count = 0
    for table_name in postgres_cols_by_table:
        if table_name in snowflake_cols_by_table:
            postgres_cols = postgres_cols_by_table[table_name]
            snowflake_cols = snowflake_cols_by_table[table_name]

            logger.info(f"📋 Processing column lineage for table: {table_name}")
            logger.info(f"   📊 PostgreSQL columns: {len(postgres_cols)}")
            logger.info(f"   ❄️ Snowflake columns: {len(snowflake_cols)}")

            # Match columns by name and create lineage
            for pg_col_name, pg_col_qualified_name in postgres_cols:
                # Find matching Snowflake column
                matching_sf_cols = [
                    (sf_col_name, sf_col_qualified_name)
                    for sf_col_name, sf_col_qualified_name in snowflake_cols
                    if sf_col_name == pg_col_name
                ]

                if matching_sf_cols:
                    sf_col_name, sf_col_qualified_name = matching_sf_cols[0]

                    try:
                        # Create column-level lineage process
                        process = Process.creator(
                            name=f"Column Mapping: {table_name}.{pg_col_name}",
                            connection_qualified_name="default/s3/1758470378",  # Use S3 connection
                            process_id=f"col_mapping_{table_name.lower()}_{pg_col_name.lower()}",
                            inputs=[
                                Column.ref_by_qualified_name(qualified_name=pg_col_qualified_name)
                            ],
                            outputs=[
                                Column.ref_by_qualified_name(qualified_name=sf_col_qualified_name)
                            ]
                        )

                        # Add process metadata
                        process.description = f"Column mapping: PostgreSQL {table_name}.{pg_col_name} → Snowflake {table_name}.{sf_col_name}"
                        process.sql = f"-- Column-level ETL for {table_name}.{pg_col_name}"

                        # Save the process
                        client.asset.save(process)
                        logger.info(f"✅ Created column lineage: {table_name}.{pg_col_name}")

                        column_lineage_count += 1

                    except Exception as e:
                        logger.error(f"❌ Error creating column lineage for {table_name}.{pg_col_name}: {e}")

    logger.info(f"🎉 Column lineage creation completed! Created {column_lineage_count} column lineage processes.")


if __name__ == "__main__":
    
    if ATLAN_API_TOKEN:
        # Show cache status
        logger.info("📊 Cache Status Check:")
        get_cache_status()

        # -------- Get all assets once ------------
        logger.info("🔍 Fetching assets from Atlan...")
        postgres_assets = find_postgres_assets()
        logger.info(f"Found {len(postgres_assets)} PostgreSQL assets")

        snowflake_assets = find_snowflake_assets()
        logger.info(f"Found {len(snowflake_assets)} Snowflake assets")

        # List S3 bucket objects
        s3_files = list_s3_bucket_objects()

        # ------ Run S3 integration workflow --------
        logger.info("🚀 Running S3 integration workflow...")
        s3_integration_result = integration_with_S3()

        if s3_integration_result:
            logger.info(f"🎉 S3 Integration Summary:")
            logger.info(f"   Connection: {s3_integration_result['connection_qualified_name']}")
            logger.info(f"   Bucket: {s3_integration_result['bucket_qualified_name']}")
            logger.info(f"   Objects Created/Updated: {s3_integration_result['object_count']}")

            # Create lineage connections
            logger.info("🔗 Creating lineage between PostgreSQL → S3 → Snowflake...")

            # Create table-level lineage
            create_table_lineage(
                postgres_assets=postgres_assets,
                s3_objects=s3_integration_result['s3_objects'],
                snowflake_assets=snowflake_assets
            )

            # Create column-level lineage
            create_column_lineage(
                postgres_assets=postgres_assets,
                snowflake_assets=snowflake_assets
            )

            logger.info("✅ Complete data lineage pipeline established successfully!")
        else:
            logger.error("❌ S3 integration failed. Cannot proceed with lineage creation.")

    else:
        print("❌ ATLAN_API_TOKEN not found. Please set your API token in .env file.")



