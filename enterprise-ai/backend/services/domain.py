import re

PUBLIC_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "proton.me", "protonmail.com", "aol.com",
    "mail.com", "zoho.com", "yandex.com", "gmx.com",
}


def email_domain(email: str) -> str:
    return (email or "").strip().lower().split("@")[-1]


def slug_from_domain(domain: str) -> str:
    base = domain.split(".")[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug or "org"


def is_public_email(email: str) -> bool:
    return email_domain(email) in PUBLIC_DOMAINS
