ROLE_SCOPES = {
    "employee": ["general"],
    "manager": ["general", "department"],
    "hr": ["general", "hr", "hr_sensitive"],
    "hr_staff": ["general", "hr"],
    "hr_manager": ["general", "hr", "hr_sensitive"],
    "stakeholder": ["general", "department", "hr", "finance", "it", "client"],
    "ceo": ["general", "department", "hr", "hr_sensitive", "finance", "finance_sensitive", "it", "client", "crm"],
    "finance_analyst": ["general", "finance"],
    "finance_head": ["general", "finance", "finance_sensitive"],
    "it_staff": ["general", "it"],
    "sales": ["general", "client"],
    "account_manager": ["general", "client", "crm"],
    "admin": ["general", "department", "hr", "hr_sensitive", "finance", "finance_sensitive", "it", "client", "crm"],
    "super_admin": ["general", "department", "hr", "hr_sensitive", "finance", "finance_sensitive", "it", "client", "crm"],
}

# Who can see / manage whom (Google Workspace / university style)
ROLE_RANK = {
    "employee": 1,
    "sales": 1,
    "it_staff": 2,
    "finance_analyst": 2,
    "manager": 3,
    "hr_staff": 3,
    "account_manager": 3,
    "hr": 4,
    "hr_manager": 4,
    "finance_head": 4,
    "stakeholder": 5,
    "admin": 6,
    "ceo": 7,
    "super_admin": 8,
}

MANAGE_USERS_ROLES = {"ceo", "admin", "hr", "hr_manager", "manager", "super_admin", "stakeholder"}
UPLOAD_ROLES = {"ceo", "admin", "hr", "hr_manager", "manager", "stakeholder", "super_admin", "finance_head"}

SENSITIVE_KEYWORDS = {
    "salary", "termination", "confidential", "board", "acquisition",
    "layoff", "compensation", "bonus", "nda",
}


def scopes_for(role: str, department: str | None = None) -> list[str]:
    scopes = list(ROLE_SCOPES.get(role, ["general"]))
    if department and "department" in scopes:
        scopes.append(department.lower())
    return scopes


def vaults_for(role: str) -> list[dict]:
    out = []
    for key, meta in DOCUMENT_VAULTS.items():
        allowed = meta["read"]
        if allowed is None or role in allowed:
            out.append({"id": key, "title": meta["title"], "blurb": meta["blurb"], "can_upload": role in meta["write"]})
    return out


def can_read_vault(role: str, vault: str) -> bool:
    meta = DOCUMENT_VAULTS.get(vault)
    if not meta:
        return vault in scopes_for(role)
    return meta["read"] is None or role in meta["read"]


def can_write_vault(role: str, vault: str) -> bool:
    meta = DOCUMENT_VAULTS.get(vault)
    if not meta:
        return False
    return role in meta["write"]


def rank(role: str) -> int:
    return ROLE_RANK.get(role or "employee", 0)


def can_manage(actor_role: str, target_role: str) -> bool:
    return rank(actor_role) > rank(target_role) or actor_role in {"ceo", "super_admin", "admin"}


def is_sensitive_query(text: str) -> bool:
    lower = (text or "").lower()
    return any(k in lower for k in SENSITIVE_KEYWORDS)
