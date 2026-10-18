"""Exercise the hosted proxy boundary without any real provider calls."""
import importlib.util
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from paylane.server import create_app
from paylane.store import Store
from paylane.domain import FIXTURE_NOW

spec = importlib.util.spec_from_file_location('deployment', Path(__file__).parents[1] / 'deployment.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)

SECRET = 'test-only-proxy-boundary-value-0000000000'
ORIGIN = 'https://paylane.example.test'

@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv('PAYLANE_ORIGIN_SECRET', SECRET)
    monkeypatch.setenv('PAYLANE_PUBLIC_ORIGIN', ORIGIN)
    monkeypatch.setenv('PAYLANE_DEMO_INVITE', 'test-invite')
    store = Store(tmp_path / 'domain.db', clock=lambda: FIXTURE_NOW)
    core = create_app(store, hosted=True, invite='test-invite', live_enabled=False)
    return deployment.create_hosted_app(base_app=core)

def test_health_is_public_but_data_requires_proxy_secret(hosted):
    with TestClient(hosted, base_url='https://api.example.test') as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/scenarios').status_code == 403
        assert client.get('/api/scenarios', headers={'X-Paylane-Origin-Secret':'wrong'}).status_code == 403
        assert client.get('/api/scenarios', headers={'X-Paylane-Origin-Secret':SECRET}).status_code == 200

def test_proxy_preserves_secure_cookies_admission_and_csrf(hosted):
    h = {'X-Paylane-Origin-Secret':SECRET, 'Origin':ORIGIN, 'Host':'forged.example.test', 'X-Forwarded-Host':'evil.example.test'}
    with TestClient(hosted, base_url='https://api.example.test') as client:
        assert client.post('/api/sessions', headers=h).status_code == 401
        login = client.post('/api/login', json={'invite':'test-invite'}, headers=h)
        assert login.status_code == 200
        cookies = login.headers.get_list('set-cookie')
        assert all('Secure' in c and 'SameSite=lax' in c for c in cookies)
        assert 'HttpOnly' in cookies[0]
        assert client.post('/api/sessions', headers=h).status_code == 403
        h['X-CSRF-Token'] = client.cookies['paylane_csrf']
        assert client.post('/api/sessions', headers=h).status_code == 200

def test_foreign_origin_and_forged_forwarded_host_are_rejected(hosted):
    with TestClient(hosted, base_url='https://api.example.test') as client:
        for origin in ['https://evil.example', 'https://paylane.example.test.evil.test', 'http://paylane.example.test', 'null']:
            h = {'X-Paylane-Origin-Secret':SECRET, 'Origin':origin, 'X-Forwarded-Host':'paylane.example.test'}
            assert client.post('/api/login', json={'invite':'test-invite'}, headers=h).status_code == 403

def test_hosted_factory_requires_private_configuration(monkeypatch):
    monkeypatch.delenv('PAYLANE_ORIGIN_SECRET', raising=False)
    with pytest.raises(ValueError, match='deployment_configuration_required'):
        deployment.create_hosted_app()
