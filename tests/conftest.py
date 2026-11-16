import os, tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATA_DIR=f"{_tmp}/data", DOCS_DIR=f"{_tmp}/docs", ADMIN_PASSWORD="adminpass1",
    SEED_DEMO="1", BACKUP_HOURS="0", BASE_URL="http://test", JWT_SECRET="test-secret", GEMINI_API_KEY="",  # empty: no LLM calls in tests
)
