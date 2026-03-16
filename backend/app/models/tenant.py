"""
Tenant and User models for multi-tenancy
"""

import os
import json
import uuid
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from ..config import Config


class TenantPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


PLAN_LIMITS = {
    TenantPlan.FREE: {"max_projects": 3, "max_simulations_per_month": 5, "max_plugins": 2},
    TenantPlan.STARTER: {"max_projects": 20, "max_simulations_per_month": 30, "max_plugins": 10},
    TenantPlan.PRO: {"max_projects": -1, "max_simulations_per_month": -1, "max_plugins": -1},
    TenantPlan.ENTERPRISE: {"max_projects": -1, "max_simulations_per_month": -1, "max_plugins": -1},
}


@dataclass
class User:
    user_id: str
    tenant_id: str
    email: str
    password_hash: str
    display_name: str
    role: str = "member"  # owner, admin, member
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
            email=data["email"],
            password_hash=data.get("password_hash", ""),
            display_name=data.get("display_name", ""),
            role=data.get("role", "member"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class TenantConfig:
    """Per-tenant configuration overrides (BYOK)"""
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model_name: Optional[str] = None
    zep_api_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_api_key": self.llm_api_key,
            "llm_base_url": self.llm_base_url,
            "llm_model_name": self.llm_model_name,
            "zep_api_key": self.zep_api_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TenantConfig':
        return cls(
            llm_api_key=data.get("llm_api_key"),
            llm_base_url=data.get("llm_base_url"),
            llm_model_name=data.get("llm_model_name"),
            zep_api_key=data.get("zep_api_key"),
        )

    def get_llm_api_key(self) -> str:
        return self.llm_api_key or Config.LLM_API_KEY

    def get_llm_base_url(self) -> str:
        return self.llm_base_url or Config.LLM_BASE_URL

    def get_llm_model_name(self) -> str:
        return self.llm_model_name or Config.LLM_MODEL_NAME

    def get_zep_api_key(self) -> str:
        return self.zep_api_key or Config.ZEP_API_KEY


@dataclass
class Tenant:
    tenant_id: str
    name: str
    plan: TenantPlan = TenantPlan.FREE
    config: TenantConfig = field(default_factory=TenantConfig)
    enabled_plugins: List[str] = field(default_factory=list)
    plugin_configs: Dict[str, Dict] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "plan": self.plan.value,
            "config": self.config.to_dict(),
            "enabled_plugins": self.enabled_plugins,
            "plugin_configs": self.plugin_configs,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Tenant':
        plan = data.get("plan", "free")
        if isinstance(plan, str):
            plan = TenantPlan(plan)
        return cls(
            tenant_id=data["tenant_id"],
            name=data.get("name", ""),
            plan=plan,
            config=TenantConfig.from_dict(data.get("config", {})),
            enabled_plugins=data.get("enabled_plugins", []),
            plugin_configs=data.get("plugin_configs", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def get_limits(self) -> Dict[str, int]:
        return PLAN_LIMITS.get(self.plan, PLAN_LIMITS[TenantPlan.FREE])


def _hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with PBKDF2-HMAC-SHA256"""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ":" + key.hex(), salt


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored hash"""
    if ":" not in stored_hash:
        return False
    salt = stored_hash.split(":")[0]
    expected, _ = _hash_password(password, salt)
    return hmac.compare_digest(stored_hash, expected)


class TenantManager:
    """Manages tenants and users on filesystem"""

    TENANTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'tenants')

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(cls.TENANTS_DIR, exist_ok=True)

    @classmethod
    def _get_tenant_dir(cls, tenant_id: str) -> str:
        return os.path.join(cls.TENANTS_DIR, tenant_id)

    @classmethod
    def _get_tenant_meta_path(cls, tenant_id: str) -> str:
        return os.path.join(cls._get_tenant_dir(tenant_id), 'tenant.json')

    @classmethod
    def _get_users_path(cls, tenant_id: str) -> str:
        return os.path.join(cls._get_tenant_dir(tenant_id), 'users.json')

    @classmethod
    def _get_tenant_data_dir(cls, tenant_id: str) -> str:
        """Root data directory for this tenant's projects/simulations/reports"""
        return os.path.join(cls._get_tenant_dir(tenant_id), 'data')

    @classmethod
    def create_tenant(cls, name: str, owner_email: str, owner_password: str,
                      owner_name: str = "") -> tuple:
        """Create a new tenant with an owner user. Returns (Tenant, User)."""
        cls._ensure_dir()

        tenant_id = f"tn_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            created_at=now,
            updated_at=now,
        )

        # Create directory structure
        tenant_dir = cls._get_tenant_dir(tenant_id)
        data_dir = cls._get_tenant_data_dir(tenant_id)
        for d in [tenant_dir, data_dir,
                  os.path.join(data_dir, 'projects'),
                  os.path.join(data_dir, 'simulations'),
                  os.path.join(data_dir, 'reports'),
                  os.path.join(data_dir, 'plugins')]:
            os.makedirs(d, exist_ok=True)

        # Save tenant
        cls.save_tenant(tenant)

        # Create owner user
        user = cls.create_user(tenant_id, owner_email, owner_password,
                               display_name=owner_name or owner_email, role="owner")

        return tenant, user

    @classmethod
    def save_tenant(cls, tenant: Tenant):
        tenant.updated_at = datetime.now().isoformat()
        meta_path = cls._get_tenant_meta_path(tenant.tenant_id)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(tenant.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def get_tenant(cls, tenant_id: str) -> Optional[Tenant]:
        meta_path = cls._get_tenant_meta_path(tenant_id)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, 'r', encoding='utf-8') as f:
            return Tenant.from_dict(json.load(f))

    @classmethod
    def create_user(cls, tenant_id: str, email: str, password: str,
                    display_name: str = "", role: str = "member") -> User:
        """Create a user within a tenant."""
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        pw_hash, _ = _hash_password(password)

        user = User(
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            password_hash=pw_hash,
            display_name=display_name or email,
            role=role,
            created_at=now,
            updated_at=now,
        )

        # Load existing users, append, save
        users = cls._load_users(tenant_id)
        users.append(user)
        cls._save_users(tenant_id, users)

        return user

    @classmethod
    def get_user_by_email(cls, email: str) -> Optional[User]:
        """Find a user by email across all tenants."""
        cls._ensure_dir()
        if not os.path.exists(cls.TENANTS_DIR):
            return None
        for tenant_id in os.listdir(cls.TENANTS_DIR):
            users = cls._load_users(tenant_id)
            for u in users:
                if u.email == email:
                    return u
        return None

    @classmethod
    def get_user(cls, user_id: str, tenant_id: str) -> Optional[User]:
        users = cls._load_users(tenant_id)
        for u in users:
            if u.user_id == user_id:
                return u
        return None

    @classmethod
    def get_user_by_id(cls, user_id: str, tenant_id: str) -> Optional[User]:
        """Find a user by user_id within a specific tenant."""
        return cls.get_user(user_id, tenant_id)

    @classmethod
    def _load_users(cls, tenant_id: str) -> List[User]:
        path = cls._get_users_path(tenant_id)
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [User.from_dict(u) for u in data]

    @classmethod
    def _save_users(cls, tenant_id: str, users: List[User]):
        path = cls._get_users_path(tenant_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump([{**u.to_dict(), "password_hash": u.password_hash} for u in users],
                      f, ensure_ascii=False, indent=2)
