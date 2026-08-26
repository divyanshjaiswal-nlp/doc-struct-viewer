"""
Copy this file to db_config.py and fill it in.

db_config.py is gitignored -- it holds database passwords, and this repo has a
GitHub remote. Never commit it.

Each top-level entry is one "key": the name that shows up in the app's Connection
dropdown. Add as many as you like.

    tenant_id   tenant to scope every query to. Leave it "" to query the schema
                without a tenant filter. If a lookup returns nothing with the
                filter on, the app retries without it and says so, so a wrong
                value here shows up as a warning rather than an empty page.
    conninfo    libpq keyword/value string WITHOUT dbname -- dbname is passed
                separately, mirroring nlp_backend/common/db_connector.py.
    dbname      database to connect to.
    schema      schema holding patient_source_document.

The connection is opened read-only (default_transaction_read_only), but a
read-only DB user is still the right thing to put here.
"""

DB_CONFIGS = {
    "example_key": {
        "tenant_id": "",
        "conninfo": "user='readonly_user' password='...' host='localhost' port='5432'",
        "dbname": "example_integration",
        "schema": "tmx_prism_trialfinder_integrations",
    },
}
