import os
import shutil
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, status, Response, Header
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
import docx
import fitz # PyMuPDF

from app.core.database import get_db
from app.core.config import settings
from app.core.security import decode_token
from app.core.exceptions import NotFoundException, ValidationException, UnauthorizedException, ForbiddenException
from app.models.models import Policy, PolicyChunk, User
from app.schemas.schemas import PolicyResponse, PolicyChunkResponse
from app.services.policy_service import PolicyService
from app.api.deps import get_current_user, get_current_hr_or_admin

router = APIRouter(prefix="/policies", tags=["Policies & Documents"])

async def get_policy_user(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
) -> User:
    """
    Authenticates requests via standard Bearer authorization header OR ?token= query parameter.
    Enables inline PDF viewing in iframes/embeds and direct file downloads.
    """
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ")[1]
    elif token:
        raw_token = token

    if not raw_token:
        raise UnauthorizedException("Missing Authorization header or token query parameter")

    try:
        payload = decode_token(raw_token)
    except Exception:
        raise UnauthorizedException("Invalid or expired authentication token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Token missing user subject")

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalars().first()
    if not user or not user.is_active:
        raise UnauthorizedException("User account is inactive or not found")

    return user

def resolve_safe_file_path(file_path: Optional[str]) -> Optional[str]:
    """
    Safely resolves a file path on disk, preventing directory traversal and handling relative paths.
    Normalizes path separators to handle Windows and Linux paths interchangeably.
    """
    if not file_path:
        return None
    if os.path.exists(file_path):
        return os.path.abspath(file_path)

    # Normalize backslashes from Windows paths
    basename = file_path.replace("\\", "/").split("/")[-1]
    if not basename:
        return None

    # Check in configured UPLOAD_DIR
    alt_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, basename))
    if os.path.exists(alt_path):
        return alt_path

    # Check relative to working directory uploads
    root_alt = os.path.abspath(os.path.join(os.getcwd(), "uploads", basename))
    if os.path.exists(root_alt):
        return root_alt

    return None

async def get_or_restore_policy_file(policy: Policy, db: AsyncSession) -> Optional[str]:
    """
    Finds the policy file on disk, or regenerates standard policy documents if missing.
    """
    real_path = resolve_safe_file_path(policy.file_path)
    if real_path and os.path.exists(real_path):
        return real_path

    # Auto-restore standard policy file if missing
    try:
        from app.core.policy_generator import ensure_physical_policy_files
        upload_dir = os.path.abspath(settings.UPLOAD_DIR)
        file_map = ensure_physical_policy_files(upload_dir)
        if policy.title in file_map and os.path.exists(file_map[policy.title]):
            real_path = file_map[policy.title]
            policy.file_path = real_path
            policy.file_size = os.path.getsize(real_path)
            await db.commit()
            return real_path
    except Exception:
        pass

    return None

def detect_mime_type(ext: str) -> str:
    ext = ext.lower()
    if ext == ".pdf":
        return "application/pdf"
    elif ext in [".docx", ".doc"]:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == ".txt":
        return "text/plain; charset=utf-8"
    return "application/octet-stream"

@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Ensure all corporate policy documents exist
    count_stmt = select(func.count(Policy.id)).where(Policy.organization_id == user.organization_id)
    existing_count = (await db.execute(count_stmt)).scalar() or 0
    if existing_count < 4:
        from app.core.policy_generator import seed_policies_if_needed
        await seed_policies_if_needed(db, user.organization_id)

    stmt = (
        select(Policy, func.count(PolicyChunk.id).label("chunk_count"))
        .outerjoin(PolicyChunk, PolicyChunk.policy_id == Policy.id)
        .where(Policy.organization_id == user.organization_id)
        .group_by(Policy.id)
        .order_by(Policy.created_at.desc())
    )
    res = await db.execute(stmt)
    output = []
    for pol, count in res.all():
        output.append({
            "id": pol.id,
            "organization_id": pol.organization_id,
            "title": pol.title,
            "category": pol.category,
            "file_path": pol.file_path,
            "file_size": pol.file_size or 0,
            "status": pol.status or "active",
            "chunk_count": count or 0,
            "created_at": pol.created_at
        })
    return output

@router.post("/upload", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def upload_policy(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("Attendance & Leave"),
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    allowed_exts = [".pdf", ".docx", ".doc", ".txt"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise ValidationException(f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_exts)}")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    saved_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, saved_filename))

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(file_path)

    policy = await PolicyService.process_document(
        db=db,
        organization_id=user.organization_id,
        title=title,
        category=category,
        file_path=file_path,
        file_size=file_size
    )

    chunk_count = (await db.execute(select(func.count(PolicyChunk.id)).where(PolicyChunk.policy_id == policy.id))).scalar_one()

    return {
        "id": policy.id,
        "organization_id": policy.organization_id,
        "title": policy.title,
        "category": policy.category,
        "file_path": policy.file_path,
        "file_size": policy.file_size,
        "status": policy.status,
        "chunk_count": chunk_count,
        "created_at": policy.created_at
    }

@router.get("/search", response_model=List[PolicyChunkResponse])
async def search_policies(
    query: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    results = await PolicyService.search_policies(
        db=db,
        organization_id=user.organization_id,
        query=query,
        limit=limit
    )
    return results

@router.get("/{policy_id}")
async def get_policy_detail(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Policy).where(
        and_(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id
        )
    )
    policy = (await db.execute(stmt)).scalars().first()
    if not policy:
        raise NotFoundException("Policy document not found")

    # Order by page_number, then id (PolicyChunk has NO chunk_index column)
    chunks_stmt = select(PolicyChunk).where(
        PolicyChunk.policy_id == policy.id
    ).order_by(PolicyChunk.page_number.asc(), PolicyChunk.id.asc())
    chunks = (await db.execute(chunks_stmt)).scalars().all()

    real_path = await get_or_restore_policy_file(policy, db)
    ext = os.path.splitext(real_path)[1].lower() if real_path else ""

    return {
        "id": policy.id,
        "title": policy.title,
        "category": policy.category,
        "file_path": policy.file_path,
        "file_size": policy.file_size or 0,
        "status": policy.status,
        "has_physical_file": bool(real_path),
        "extension": ext.lstrip("."),
        "chunk_count": len(chunks),
        "created_at": policy.created_at,
        "chunks": [
            {
                "id": c.id,
                "page_number": c.page_number,
                "section": c.section,
                "content": c.content,
                "token_count": c.token_count
            }
            for c in chunks
        ]
    }

@router.get("/{policy_id}/content")
async def get_policy_content(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns rich, structured content for the interactive document viewer.
    Extracts paragraphs, headings, and tables from DOCX, or pages from PDF,
    with a graceful fallback to indexed policy chunks.
    """
    stmt = select(Policy).where(
        and_(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id
        )
    )
    policy = (await db.execute(stmt)).scalars().first()
    if not policy:
        raise NotFoundException("Policy document not found")

    chunks_stmt = select(PolicyChunk).where(
        PolicyChunk.policy_id == policy.id
    ).order_by(PolicyChunk.page_number.asc(), PolicyChunk.id.asc())
    chunks = (await db.execute(chunks_stmt)).scalars().all()

    real_path = await get_or_restore_policy_file(policy, db)
    ext = os.path.splitext(real_path)[1].lower() if real_path else ""

    doc_format = "chunk"
    total_pages = max([c.page_number for c in chunks] or [1])
    elements: List[Dict[str, Any]] = []

    if real_path and ext == ".pdf":
        doc_format = "pdf"
        try:
            pdf_doc = fitz.open(real_path)
            total_pages = len(pdf_doc)
            for page_idx in range(len(pdf_doc)):
                page = pdf_doc[page_idx]
                text = page.get_text().strip()
                elements.append({
                    "type": "page",
                    "page_number": page_idx + 1,
                    "text": text
                })
            pdf_doc.close()
        except Exception:
            # Fallback to chunks
            elements = [
                {"type": "page", "page_number": c.page_number, "section": c.section, "text": c.content}
                for c in chunks
            ]
    elif real_path and ext in [".docx", ".doc"]:
        doc_format = "docx"
        try:
            doc = docx.Document(real_path)
            for p in doc.paragraphs:
                text = p.text.strip()
                if not text:
                    continue
                style_name = p.style.name.lower() if p.style else "normal"
                if "heading 1" in style_name or "title" in style_name:
                    elements.append({"type": "heading1", "text": text})
                elif "heading 2" in style_name:
                    elements.append({"type": "heading2", "text": text})
                elif "heading 3" in style_name:
                    elements.append({"type": "heading3", "text": text})
                else:
                    elements.append({"type": "paragraph", "text": text})

            for t in doc.tables:
                rows_data = []
                for row in t.rows:
                    rows_data.append([cell.text.strip() for cell in row.cells])
                if rows_data:
                    elements.append({"type": "table", "rows": rows_data})
        except Exception:
            elements = [
                {"type": "paragraph", "text": c.content}
                for c in chunks
            ]
    elif real_path and ext == ".txt":
        doc_format = "txt"
        try:
            with open(real_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            elements = [{"type": "paragraph", "text": l} for l in lines]
        except Exception:
            elements = [{"type": "paragraph", "text": c.content} for c in chunks]
    else:
        # Fallback to chunk database records
        elements = [
            {"type": "page", "page_number": c.page_number, "section": c.section, "text": c.content}
            for c in chunks
        ]

    return {
        "id": policy.id,
        "title": policy.title,
        "category": policy.category,
        "format": doc_format,
        "file_size": policy.file_size or (os.path.getsize(real_path) if real_path else 0),
        "total_pages": total_pages,
        "elements_count": len(elements),
        "elements": elements,
        "download_url": f"/api/v1/policies/{policy.id}/download",
        "view_url": f"/api/v1/policies/{policy.id}/view"
    }

@router.get("/{policy_id}/view")
async def view_policy(
    policy_id: str,
    user: User = Depends(get_policy_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Streams the policy file inline for viewing within browser iframes / embeds.
    Supports both Bearer authorization header and ?token= query parameter.
    """
    stmt = select(Policy).where(
        and_(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id
        )
    )
    policy = (await db.execute(stmt)).scalars().first()
    if not policy:
        raise NotFoundException("Policy document not found")

    real_path = await get_or_restore_policy_file(policy, db)
    if real_path and os.path.exists(real_path):
        ext = os.path.splitext(real_path)[1].lower()
        media_type = detect_mime_type(ext)
        clean_filename = f"{policy.title}{ext}"
        return FileResponse(
            path=real_path,
            filename=clean_filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{clean_filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    # Fallback: render text content from chunks inline
    chunks_stmt = select(PolicyChunk).where(
        PolicyChunk.policy_id == policy.id
    ).order_by(PolicyChunk.page_number.asc(), PolicyChunk.id.asc())
    chunks = (await db.execute(chunks_stmt)).scalars().all()
    full_text = "\n\n".join([f"--- Page {c.page_number} ({c.section or 'General'}) ---\n{c.content}" for c in chunks])
    return Response(
        content=full_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{policy.title}.txt"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.get("/{policy_id}/download")
async def download_policy(
    policy_id: str,
    user: User = Depends(get_policy_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Downloads the original policy document with proper Content-Type and Content-Disposition.
    Supports both Bearer authorization header and ?token= query parameter.
    """
    stmt = select(Policy).where(
        and_(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id
        )
    )
    policy = (await db.execute(stmt)).scalars().first()
    if not policy:
        raise NotFoundException("Policy document not found")

    real_path = await get_or_restore_policy_file(policy, db)
    if real_path and os.path.exists(real_path):
        ext = os.path.splitext(real_path)[1].lower()
        media_type = detect_mime_type(ext)
        clean_filename = f"{policy.title}{ext}"
        file_size = os.path.getsize(real_path)
        return FileResponse(
            path=real_path,
            filename=clean_filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{clean_filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Length",
                "Content-Length": str(file_size)
            }
        )

    # Fallback to generating text attachment from chunks
    chunks_stmt = select(PolicyChunk).where(
        PolicyChunk.policy_id == policy.id
    ).order_by(PolicyChunk.page_number.asc(), PolicyChunk.id.asc())
    chunks = (await db.execute(chunks_stmt)).scalars().all()
    full_text = "\n\n".join([f"--- Page {c.page_number} ({c.section or 'Section'}) ---\n{c.content}" for c in chunks])
    content_bytes = full_text.encode("utf-8")
    return Response(
        content=content_bytes,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{policy.title}.txt"',
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Length",
            "Content-Length": str(len(content_bytes))
        }
    )

@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Policy).where(
        and_(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id
        )
    )
    pol = (await db.execute(stmt)).scalars().first()
    if not pol:
        raise NotFoundException("Policy not found")

    real_path = resolve_safe_file_path(pol.file_path)
    if real_path and os.path.exists(real_path):
        try:
            os.remove(real_path)
        except Exception:
            pass

    await db.delete(pol)
    await db.commit()
    return {"message": "Policy document deleted successfully"}
