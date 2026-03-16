"""
Tests for authentication endpoints and JWT middleware.
"""

import os
import time
import shutil
import tempfile

import pytest

# Use a temp upload folder so tests don't touch real data
_TEMP_DIR = tempfile.mkdtemp()
os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ['JWT_EXPIRY_HOURS'] = '48'

# Patch UPLOAD_FOLDER before importing app
import app.config as _cfg
_cfg.Config.UPLOAD_FOLDER = _TEMP_DIR


from app import create_app  # noqa: E402
from app.models.tenant import TenantManager  # noqa: E402

TenantManager.TENANTS_DIR = os.path.join(_TEMP_DIR, 'tenants')


@pytest.fixture(scope='module')
def client():
    application = create_app()
    application.config['TESTING'] = True
    with application.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_tenants():
    """Remove tenant data between tests."""
    yield
    if os.path.exists(TenantManager.TENANTS_DIR):
        shutil.rmtree(TenantManager.TENANTS_DIR)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def test_register_success(client):
    resp = client.post('/api/auth/register', json={
        'email': 'owner@example.com',
        'password': 'secret123',
        'display_name': 'Owner',
        'tenant_name': 'Acme',
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert 'access_token' in data
    assert data['user']['email'] == 'owner@example.com'
    assert data['user']['role'] == 'owner'
    assert data['tenant']['name'] == 'Acme'


def test_register_duplicate_email(client):
    payload = {
        'email': 'dup@example.com',
        'password': 'pass',
        'display_name': 'D',
        'tenant_name': 'T1',
    }
    client.post('/api/auth/register', json=payload)
    resp = client.post('/api/auth/register', json={**payload, 'tenant_name': 'T2'})
    assert resp.status_code == 409


def test_register_missing_fields(client):
    resp = client.post('/api/auth/register', json={'email': 'a@b.com'})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

def test_login_success(client):
    client.post('/api/auth/register', json={
        'email': 'login@example.com',
        'password': 'pass123',
        'display_name': 'L',
        'tenant_name': 'LT',
    })
    resp = client.post('/api/auth/login', json={
        'email': 'login@example.com',
        'password': 'pass123',
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'access_token' in data


def test_login_wrong_password(client):
    client.post('/api/auth/register', json={
        'email': 'wp@example.com',
        'password': 'correct',
        'display_name': 'W',
        'tenant_name': 'WT',
    })
    resp = client.post('/api/auth/login', json={
        'email': 'wp@example.com',
        'password': 'wrong',
    })
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post('/api/auth/login', json={
        'email': 'nobody@example.com',
        'password': 'x',
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------

def _get_token(client, email='me@example.com', password='pw', tenant='MT'):
    client.post('/api/auth/register', json={
        'email': email,
        'password': password,
        'display_name': 'Me',
        'tenant_name': tenant,
    })
    r = client.post('/api/auth/login', json={'email': email, 'password': password})
    return r.get_json()['access_token']


def test_auth_me(client):
    token = _get_token(client, 'me@example.com', 'pw', 'MT')
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['user']['email'] == 'me@example.com'


def test_auth_me_no_token(client):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 401


def test_auth_me_bad_token(client):
    resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer notavalidtoken'})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected route requires auth
# ---------------------------------------------------------------------------

def test_graph_route_requires_auth(client):
    resp = client.get('/api/graph/project/list')
    assert resp.status_code == 401


def test_simulation_route_requires_auth(client):
    resp = client.get('/api/simulation/list')
    assert resp.status_code == 401


def test_report_route_requires_auth(client):
    resp = client.get('/api/report/list')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------

def test_expired_token_returns_401(client):
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta

    payload = {
        'sub': 'usr_test',
        'tenant_id': 'tn_test',
        'email': 'exp@example.com',
        'role': 'owner',
        'exp': datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    token = pyjwt.encode(payload, 'test-secret', algorithm='HS256')
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 401
