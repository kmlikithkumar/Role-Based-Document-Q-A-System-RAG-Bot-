"""Off-site backup to an S3-compatible server (moto) and clear error reporting."""
import sys

import boto3
import httpx

from tests.integration.helpers import Proc, free_port, login, start_app, wait_port


def test_backup_reports_offsite_result():
    port = free_port()
    moto = Proc([sys.executable, "-m", "moto.server", "-p", str(port)])
    wait_port(port)
    ep = f"http://127.0.0.1:{port}"
    creds = dict(AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="y", AWS_DEFAULT_REGION="us-east-1")
    s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id="x", aws_secret_access_key="y", region_name="us-east-1")
    s3.create_bucket(Bucket="backup-bucket")
    good, url = start_app(BACKUP_S3_BUCKET="backup-bucket", S3_ENDPOINT_URL=ep, BACKUP_PASSPHRASE="pw", **creds)
    bad, url2 = start_app(BACKUP_S3_BUCKET="no-such-bucket", S3_ENDPOINT_URL=ep, **creds)
    try:
        r = httpx.post(url + "/api/backup", headers=login(url, "admin", "adminpass1"), timeout=60).json()
        assert r["offsite"] is True
        assert [o["Key"] for o in s3.list_objects_v2(Bucket="backup-bucket")["Contents"]] == ["docsbot/" + r["name"]]
        r2 = httpx.post(url2 + "/api/backup", headers=login(url2, "admin", "adminpass1"), timeout=60).json()
        assert r2["offsite"] is False and r2["offsite_error"]
    finally:
        good.stop(); bad.stop(); moto.stop()
