from fastapi.testclient import TestClient

from jarvis.config import Settings
from jarvis.main import create_app


def test_interface_assets_and_no_credentials(tmp_path):
    settings = Settings(_env_file=None, api_token="private-test-token",
                        provider_api_key="private-provider-key", database_path=str(tmp_path / "db.sqlite3"))
    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Command center" in page.text
        assert "private-test-token" not in page.text
        assert "private-provider-key" not in page.text
        assert client.get("/assets/style.css").status_code == 200
        script = client.get("/assets/app.js")
        assert script.status_code == 200
        assert "private-test-token" not in script.text
        assert client.get("/assets/../config.py").status_code == 404
