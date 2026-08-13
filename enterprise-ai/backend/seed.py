from sqlalchemy import select
from config import settings
from models.document import Document
from models.tenant import Tenant
from models.user import User
from services.auth_service import hash_password
from services.ingest_service import ingest_document
from services.rag_service import collection_for


async def seed_if_needed(db):
    existing = await db.scalar(select(Tenant).where(Tenant.tenant_id == "platform"))
    if not existing:
        db.add(
            Tenant(
                tenant_id="platform",
                company_name="Enterprise AI Platform",
                subdomain="admin",
                support_email=settings.SUPER_ADMIN_EMAIL,
                admin_email=settings.SUPER_ADMIN_EMAIL,
                vector_namespace="ns_platform",
                sso_provider="local",
                email_domain="ent-ai.local",
                is_active=True,
            )
        )
        db.add(
            User(
                tenant_id="platform",
                email=settings.SUPER_ADMIN_EMAIL,
                name="Platform Super Admin",
                hashed_password=hash_password(settings.SUPER_ADMIN_PASSWORD),
                role="super_admin",
                department="platform",
                is_active=True,
            )
        )
        await db.commit()

    if not settings.SEED_DEMO:
        return

    for tid, name, support in [
        ("wipro", "Wipro Limited", "it-support@wipro.com"),
        ("tcs", "Tata Consultancy Services", "helpdesk@tcs.com"),
        ("infosys", "Infosys Limited", "askhr@infosys.com"),
    ]:
        t = await db.scalar(select(Tenant).where(Tenant.tenant_id == tid))
        if t:
            continue
        db.add(
            Tenant(
                tenant_id=tid,
                company_name=name,
                subdomain=tid,
                support_email=support,
                admin_email=f"admin@{tid}.com",
                vector_namespace=f"ns_{tid}",
                sso_provider="local",
                email_domain=f"{tid}.com",
                is_active=True,
            )
        )
        users = [
            (f"admin@{tid}.com", "Tenant Admin", "admin", "IT"),
            (f"hr@{tid}.com", "HR Manager", "hr_manager", "HR"),
            (f"finance@{tid}.com", "Finance Head", "finance_head", "Finance"),
            (f"emp@{tid}.com", "Employee", "employee", "Engineering"),
        ]
        for email, uname, role, dept in users:
            db.add(
                User(
                    tenant_id=tid,
                    email=email,
                    name=uname,
                    hashed_password=hash_password("Password@123"),
                    role=role,
                    department=dept,
                    is_active=True,
                )
            )
        await db.commit()

    await _seed_demo_docs(db)


DEMO_DOCS = {
    "wipro": (
        "wipro_leave_policy.txt",
        "general",
        """Wipro Limited — Leave Policy (HR Handbook excerpt)
Employees are entitled to 21 days of earned leave per calendar year.
Casual leave: 8 days. Sick leave: 12 days with medical certificate after 2 consecutive days.
Maternity leave: 26 weeks. Paternity leave: 7 working days.
Leave applications must be submitted in MyWipro at least 3 days in advance except emergencies.
Unused earned leave can be encashed up to 15 days at year end with manager approval.
""",
    ),
    "tcs": (
        "tcs_code_of_conduct.txt",
        "general",
        """Tata Consultancy Services — Code of Conduct
Associates must protect client confidential information and never share credentials.
Gifts above INR 2000 require compliance approval.
Work from office is 3 days per week unless the account mandates otherwise (TCS Secure Borderless Workspaces).
The ethics helpline is available 24x7 via ethics@tcs.com.
""",
    ),
    "apexforge": (
        "apex_employee_handbook.txt",
        "general",
        """Apex Forge — Employee Handbook
Working hours are 9:30 to 18:30 IST, Monday to Friday, with a hybrid model of 3 days in office.
Earned leave: 20 days per year. Casual leave: 7 days. Sick leave: 10 days.
Leave is requested in Workday at least 2 days in advance.
The employee helpdesk is people@apexforge.com.
Engineering uses GitHub Enterprise. Production access requires manager approval.
Salary discussions are confidential and handled only by HR.
""",
    ),
    "infosys": (
        "infosys_it_policy.txt",
        "it",
        """Infosys Limited — IT Acceptable Use Policy
Company laptops must have Infosys endpoint protection enabled.
USB storage is disabled on production networks.
VPN (Pulse) is mandatory off-campus.
Password rotation every 90 days. MFA required for all SaaS tools.
Report incidents to askhr@infosys.com and the SOC within 1 hour.
""",
    ),
}


async def _seed_demo_docs(db):
    for tid, (fname, access, text) in DEMO_DOCS.items():
        t = await db.scalar(select(Tenant).where(Tenant.tenant_id == tid))
        if not t:
            continue
        exists = await db.scalar(select(Document).where(Document.tenant_id == tid, Document.filename == fname))
        if exists:
            continue
        try:
            collection_for(t.vector_namespace)
            doc_id, n = ingest_document(
                text.encode(), fname, tid, t.vector_namespace, "HR" if access == "general" else "IT", access
            )
            db.add(
                Document(
                    doc_id=doc_id,
                    tenant_id=tid,
                    filename=fname,
                    file_type="txt",
                    department="HR",
                    access_level=access,
                    chunk_count=n,
                )
            )
            await db.commit()
        except Exception as e:
            print("seed doc skip", tid, e)
