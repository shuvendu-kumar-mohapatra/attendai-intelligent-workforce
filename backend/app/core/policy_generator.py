import os
import uuid
import logging
from typing import Dict, Any, List, Optional
import pymupdf as fitz
import docx
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Organization, Policy, PolicyChunk

logger = logging.getLogger("attendai.policies")

POLICY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "title": "AttendAI Global Attendance and Working Hours Policy",
        "category": "Attendance & Punctuality",
        "filename": "Global_Attendance_Policy.pdf",
        "mime_type": "application/pdf",
        "chunks": [
            {
                "section": "Core Working Hours",
                "page_number": 1,
                "content": (
                    "AttendAI core working hours are established between 09:00 and 17:30 local time. "
                    "Employees are expected to clock in using the AttendAI portal upon starting work "
                    "and clock out when completing daily duties. A standard working day consists of "
                    "8 productive hours plus a 30-minute to 1-hour lunch break."
                )
            },
            {
                "section": "Punctuality and Grace Periods",
                "page_number": 1,
                "content": (
                    "A grace period of 15 minutes is allowed for clock-in beyond scheduled shift start. "
                    "Clock-ins occurring 16 minutes or more after the shift commencement are flagged "
                    "as Late Arrivals. Repeated late arrivals exceeding 3 occurrences within a rolling "
                    "7-day period are automatically surfaced to HR managers for review."
                )
            },
            {
                "section": "Overtime Rules and Eligibility",
                "page_number": 2,
                "content": (
                    "Overtime commences once total worked duration in a calendar day exceeds the scheduled "
                    "required shift hours (typically 8.0 hours). Overtime must be pre-authorized by department "
                    "managers. Non-exempt employees will receive compensation or compensatory time-off in "
                    "accordance with local labor standards."
                )
            }
        ]
    },
    {
        "title": "Comprehensive Leave and Time-Off Guidelines",
        "category": "Leave Management",
        "filename": "Comprehensive_Leave_Guidelines.pdf",
        "mime_type": "application/pdf",
        "chunks": [
            {
                "section": "Annual Leave Allocation",
                "page_number": 1,
                "content": (
                    "Full-time employees accrue 20 days of paid annual leave per calendar year. "
                    "Annual leave requests should be submitted at least 5 business days in advance "
                    "via the AttendAI Leave portal and require supervisor approval. Unused leave balances "
                    "up to a maximum of 5 days can carry over into the following fiscal year."
                )
            },
            {
                "section": "Sick and Emergency Leave",
                "page_number": 2,
                "content": (
                    "Employees are granted 10 days of paid sick leave per year. Medical certificates "
                    "are required for consecutive sick leaves exceeding 3 business days. "
                    "Emergency personal leaves can be approved retrospectively upon manager consultation. "
                    "Compassionate bereavement leave allows up to 5 consecutive paid days off."
                )
            }
        ]
    },
    {
        "title": "Remote Work Guidelines 2026",
        "category": "Remote Work",
        "filename": "Remote_Work_Policy.pdf",
        "mime_type": "application/pdf",
        "chunks": [
            {
                "section": "Eligibility and Scheduling",
                "page_number": 1,
                "content": (
                    "AttendAI Remote Work Policy Document 2026.\n"
                    "Employees may request up to two remote days per week with manager pre-approval. "
                    "Remote work requests must be logged through the scheduling module at least 48 hours in advance. "
                    "Eligibility requires completion of probation and maintaining satisfactory punctuality scores."
                )
            },
            {
                "section": "Core Working Hours and Daily Standups",
                "page_number": 2,
                "content": (
                    "Core working hours for remote staff are 10:00 AM to 4:00 PM EST.\n"
                    "Daily standup attendance is mandatory regardless of work location. "
                    "Employees must remain reachable via Slack and AttendAI communications during core hours, "
                    "and connect strictly through enterprise VPN security protocols."
                )
            }
        ]
    },
    {
        "title": "Workplace Code of Conduct",
        "category": "Compliance",
        "filename": "Code_of_Conduct.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "chunks": [
            {
                "section": "Safe and Respectful Workplace",
                "page_number": 1,
                "content": (
                    "AttendAI Code of Conduct and Anti-Harassment\n"
                    "AttendAI is committed to providing a safe, inclusive, and respectful work environment for all personnel. "
                    "Workplace bullying, harassment, and discrimination of any kind based on protected characteristics "
                    "are strictly prohibited and subject to immediate disciplinary termination.\n"
                    "Reports can be filed anonymously with the HR Compliance Office via hr-compliance@attendai.com."
                )
            },
            {
                "section": "Information Security and Data Governance",
                "page_number": 1,
                "content": (
                    "Personnel must safeguard confidential corporate intelligence, customer records, and biometric telemetry "
                    "in accordance with SOC2 Type II, ISO 27001, and GDPR standards. Company-issued workstations must remain "
                    "encrypted with full-disk BitLocker/FileVault security and MFA enabled on all systems."
                )
            }
        ]
    }
]

def generate_pdf_document(title: str, category: str, chunks: List[Dict[str, Any]], output_path: str) -> None:
    """Generates a professional multi-page PDF document using PyMuPDF."""
    doc = fitz.open()

    # Group chunks by page_number
    pages_map: Dict[int, List[Dict[str, Any]]] = {}
    for c in chunks:
        p_num = c.get("page_number", 1)
        pages_map.setdefault(p_num, []).append(c)

    total_pages = max(pages_map.keys()) if pages_map else 1

    for page_num in range(1, total_pages + 1):
        page = doc.new_page(width=595, height=842) # A4
        # Header banner
        page.insert_text((50, 50), title, fontsize=15, fontname="helv", color=(0.06, 0.2, 0.38))
        page.insert_text((50, 70), f"Category: {category} • AttendAI Official Workforce Policy", fontsize=9, fontname="helv", color=(0.4, 0.45, 0.5))
        page.draw_line((50, 80), (545, 80), color=(0.82, 0.85, 0.88), width=1)

        y_pos = 110
        chunks_on_page = pages_map.get(page_num, [])
        for chunk in chunks_on_page:
            sec_title = chunk.get("section", f"Section {page_num}")
            sec_content = chunk.get("content", "")

            # Section heading
            page.insert_text((50, y_pos), sec_title, fontsize=11, fontname="helv", color=(0.1, 0.15, 0.2))
            y_pos += 18

            # Section body
            rect = fitz.Rect(50, y_pos, 545, y_pos + 120)
            page.insert_textbox(rect, sec_content, fontsize=9.5, fontname="helv", color=(0.25, 0.28, 0.32))
            y_pos += 130

        # Footer
        page.draw_line((50, 790), (545, 790), color=(0.88, 0.9, 0.92), width=0.5)
        page.insert_text((50, 805), f"Page {page_num} of {total_pages} • AttendAI Corporation Confidential", fontsize=8, fontname="helv", color=(0.55, 0.6, 0.65))

    doc.save(output_path)
    doc.close()

def generate_docx_document(title: str, category: str, chunks: List[Dict[str, Any]], output_path: str) -> None:
    """Generates a professional DOCX document using python-docx."""
    doc = docx.Document()

    doc.add_heading(title, 0)
    meta_p = doc.add_paragraph(f"Category: {category} • Version 2026.1 • AttendAI Official Policy")
    meta_p.italic = True

    for idx, c in enumerate(chunks, 1):
        doc.add_heading(f"{idx}. {c.get('section', 'Section')}", level=1)
        doc.add_paragraph(c.get("content", ""))

    # Governance Summary Table
    doc.add_heading("Corporate Compliance & Governance", level=2)
    table = doc.add_table(rows=1, cols=3)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Governance Area"
    hdr_cells[1].text = "Standard"
    hdr_cells[2].text = "Enforcement Authority"

    rows = [
        ("Anti-Harassment & Ethics", "Zero Tolerance", "HR Compliance Board"),
        ("Data Security & Privacy", "SOC2 Type II / ISO 27001", "InfoSec Operations"),
        ("Workforce Punctuality", "Standard Shift Grace Policy", "Workforce Operations")
    ]
    for area, std, auth in rows:
        r_cells = table.add_row().cells
        r_cells[0].text = area
        r_cells[1].text = std
        r_cells[2].text = auth

    doc.save(output_path)

def ensure_physical_policy_files(target_dir: str) -> Dict[str, str]:
    """
    Ensures that all 4 policy files exist in target_dir.
    If missing or empty, copies from bundled sample_documents or generates them on disk.
    Returns mapping: {policy_title: absolute_file_path}
    """
    os.makedirs(target_dir, exist_ok=True)
    generated_map: Dict[str, str] = {}
    sample_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sample_documents"))

    for pol in POLICY_DEFINITIONS:
        title = pol["title"]
        filename = pol["filename"]
        out_path = os.path.abspath(os.path.join(target_dir, filename))

        need_generate = not os.path.exists(out_path) or os.path.getsize(out_path) == 0

        if need_generate:
            bundled_sample = os.path.join(sample_dir, filename)
            if os.path.exists(bundled_sample) and os.path.getsize(bundled_sample) > 0:
                import shutil
                shutil.copyfile(bundled_sample, out_path)
                logger.info(f"Copied bundled policy document: {bundled_sample} -> {out_path}")
            else:
                try:
                    if filename.endswith(".pdf"):
                        generate_pdf_document(title, pol["category"], pol["chunks"], out_path)
                    elif filename.endswith(".docx"):
                        generate_docx_document(title, pol["category"], pol["chunks"], out_path)
                    logger.info(f"Generated policy document file: {out_path} ({os.path.getsize(out_path)} bytes)")
                except Exception as e:
                    logger.error(f"Failed to generate policy file '{filename}': {e}", exc_info=True)

        generated_map[title] = out_path

    return generated_map

async def seed_policies_if_needed(db: AsyncSession, org_id: Optional[str] = None) -> int:
    """
    Idempotently seeds all 4 corporate policy documents into the database
    and ensures their physical PDF/DOCX files exist on disk in settings.UPLOAD_DIR.
    Safe to call repeatedly on every backend boot.
    """
    upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    file_map = ensure_physical_policy_files(upload_dir)

    # Determine organizations to seed
    if org_id:
        org_ids = [org_id]
    else:
        stmt = select(Organization.id)
        org_ids = (await db.execute(stmt)).scalars().all()
        if not org_ids:
            # Fallback: create default organization if none exists
            default_org = Organization(
                id=str(uuid.uuid4()),
                name="AttendAI Global Technologies",
                timezone="UTC"
            )
            db.add(default_org)
            await db.flush()
            org_ids = [default_org.id]

    policies_created_or_updated = 0

    for oid in org_ids:
        for pol_def in POLICY_DEFINITIONS:
            title = pol_def["title"]
            category = pol_def["category"]
            filename = pol_def["filename"]
            file_path = file_map.get(title) or os.path.abspath(os.path.join(upload_dir, filename))
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 10240

            # Check if this policy already exists (deduplicating if multiple exist)
            stmt = select(Policy).where(
                Policy.organization_id == oid,
                Policy.title == title
            ).order_by(Policy.created_at.asc())
            existing_policies = (await db.execute(stmt)).scalars().all()

            if existing_policies:
                canonical_policy = existing_policies[0]
                # Clean up any redundant duplicate policy rows
                for dup in existing_policies[1:]:
                    await db.execute(delete(PolicyChunk).where(PolicyChunk.policy_id == dup.id))
                    await db.delete(dup)
                    logger.info(f"Deduplicated excess policy row {dup.id} for '{title}'")

                existing_policy = canonical_policy
                # Ensure physical path and size are accurate
                updated = False
                if not existing_policy.file_path or not os.path.exists(existing_policy.file_path):
                    existing_policy.file_path = file_path
                    existing_policy.file_size = file_size
                    updated = True
                if existing_policy.status != "active":
                    existing_policy.status = "active"
                    updated = True

                # Check if chunks exist
                chunk_count = (await db.execute(
                    select(func.count(PolicyChunk.id)).where(PolicyChunk.policy_id == existing_policy.id)
                )).scalar() or 0

                if chunk_count < len(pol_def["chunks"]):
                    # Refresh chunks
                    await db.execute(delete(PolicyChunk).where(PolicyChunk.policy_id == existing_policy.id))
                    for c in pol_def["chunks"]:
                        content = c["content"]
                        db.add(PolicyChunk(
                            id=str(uuid.uuid4()),
                            policy_id=existing_policy.id,
                            title=title,
                            section=c["section"],
                            page_number=c["page_number"],
                            content=content,
                            token_count=len(content.split())
                        ))
                    updated = True

                if updated:
                    policies_created_or_updated += 1
            else:
                # Create brand new policy
                pol_id = str(uuid.uuid4())
                new_policy = Policy(
                    id=pol_id,
                    organization_id=oid,
                    title=title,
                    category=category,
                    file_path=file_path,
                    file_size=file_size,
                    status="active"
                )
                db.add(new_policy)
                await db.flush()

                for c in pol_def["chunks"]:
                    content = c["content"]
                    db.add(PolicyChunk(
                        id=str(uuid.uuid4()),
                        policy_id=pol_id,
                        title=title,
                        section=c["section"],
                        page_number=c["page_number"],
                        content=content,
                        token_count=len(content.split())
                    ))
                policies_created_or_updated += 1

    await db.commit()
    logger.info(f"seed_policies_if_needed: processed {len(POLICY_DEFINITIONS)} policies across {len(org_ids)} org(s) ({policies_created_or_updated} created/updated).")
    return policies_created_or_updated
