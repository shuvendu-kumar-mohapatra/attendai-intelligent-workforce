import os
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from app.models.models import Policy, PolicyChunk
from app.core.exceptions import ValidationException, NotFoundException

class PolicyService:
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> List[Dict[str, Any]]:
        """Extract pages from PDF using PyMuPDF preserving layout, page numbers and section headers."""
        pages = []
        if not file_path or not os.path.exists(file_path):
            raise ValidationException(f"PDF file not found at path: {file_path}")
        try:
            import pymupdf as fitz
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_content = page.get_text("text")
                if text_content and text_content.strip():
                    # Attempt to detect section header from first non-empty line
                    lines = [l.strip() for l in text_content.split("\n") if l.strip()]
                    first_line = lines[0] if lines else f"Page {page_num + 1}"
                    section_title = first_line[:80] if len(first_line) > 3 else f"Section {page_num + 1}"
                    pages.append({
                        "page_number": page_num + 1,
                        "section": section_title,
                        "content": text_content.strip()
                    })
            doc.close()
        except ValidationException:
            raise
        except Exception as e:
            raise ValidationException(f"Failed to extract text from PDF: {str(e)}")
        return pages

    @staticmethod
    def extract_text_from_docx(file_path: str) -> List[Dict[str, Any]]:
        """Extract structured sections and tables from DOCX using python-docx."""
        pages = []
        if not file_path or not os.path.exists(file_path):
            raise ValidationException(f"DOCX file not found at path: {file_path}")
        try:
            import docx
            doc = docx.Document(file_path)
            body_parts = []
            for p in doc.paragraphs:
                p_text = p.text.strip()
                if p_text:
                    body_parts.append(p_text)

            # Include text from all tables
            for t in doc.tables:
                for row in t.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        body_parts.append(" | ".join(row_cells))

            full_text = "\n\n".join(body_parts)
            if full_text.strip():
                # Split roughly every 1500 chars to simulate pages/sections
                chunks = [full_text[i:i+1500] for i in range(0, len(full_text), 1500)]
                for idx, c in enumerate(chunks):
                    lines = [l.strip() for l in c.split("\n") if l.strip()]
                    section_title = lines[0][:80] if lines else f"Section {idx + 1}"
                    pages.append({
                        "page_number": idx + 1,
                        "section": section_title,
                        "content": c.strip()
                    })
        except ValidationException:
            raise
        except Exception as e:
            raise ValidationException(f"Failed to extract text from DOCX: {str(e)}")
        return pages

    @staticmethod
    async def process_document(
        db: AsyncSession,
        organization_id: str,
        title: str,
        category: str,
        file_path: str,
        file_size: int
    ) -> Policy:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                extracted = PolicyService.extract_text_from_pdf(file_path)
            elif ext in [".docx", ".doc"]:
                extracted = PolicyService.extract_text_from_docx(file_path)
            elif ext == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                extracted = [{"page_number": 1, "section": "General", "content": content.strip()}] if content.strip() else []
            else:
                raise ValidationException(f"Unsupported file format: {ext}. Only PDF, DOCX, and TXT are supported.")
        except Exception as ex:
            # Transactionally store failed policy with clear failed status
            failed_policy = Policy(
                organization_id=organization_id,
                title=title,
                category=category,
                file_path=file_path,
                file_size=file_size,
                status="failed"
            )
            db.add(failed_policy)
            await db.commit()
            await db.refresh(failed_policy)
            raise ValidationException(f"Document ingestion failed: {str(ex)}")

        # Status is active if text was extracted, empty if 0 text extracted
        doc_status = "active" if extracted and any(item.get("content", "").strip() for item in extracted) else "empty"

        policy = Policy(
            organization_id=organization_id,
            title=title,
            category=category,
            file_path=file_path,
            file_size=file_size,
            status=doc_status
        )
        db.add(policy)
        await db.flush()

        for item in extracted:
            content = item["content"].strip()
            if content:
                chunk = PolicyChunk(
                    policy_id=policy.id,
                    title=title,
                    section=item.get("section") or f"Section {item['page_number']}",
                    page_number=item["page_number"],
                    content=content,
                    token_count=len(content.split())
                )
                db.add(chunk)

        await db.commit()
        await db.refresh(policy)
        return policy

    @staticmethod
    async def search_policies(
        db: AsyncSession,
        organization_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Full text search with metadata and source citations.
        Supports SQLite (like/instr) and PostgreSQL (ILIKE or tsvector).
        """
        terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 2]
        if not terms:
            terms = [query.lower()]

        # Search chunks joined with policy
        stmt = (
            select(PolicyChunk, Policy)
            .join(Policy, Policy.id == PolicyChunk.policy_id)
            .where(Policy.organization_id == organization_id)
        )
        
        # Build search condition
        conditions = []
        for term in terms:
            conditions.append(PolicyChunk.content.ilike(f"%{term}%"))
            conditions.append(Policy.title.ilike(f"%{term}%"))
            
        if conditions:
            stmt = stmt.where(or_(*conditions))

        # Fetch candidates to rank by relevance
        stmt = stmt.limit(max(limit * 3, 20))
        results = await db.execute(stmt)
        
        raw_items = []
        for chunk, policy in results.all():
            p_title = policy.title.lower()
            c_content = chunk.content.lower()
            q_lower = query.lower()

            # Relevance scoring
            score = 0
            if q_lower in p_title:
                score += 100
            if q_lower in c_content:
                score += 50
            if all(t in c_content or t in p_title for t in terms):
                score += 30
            for t in terms:
                if t in p_title:
                    score += 15
                if t in c_content:
                    score += 5

            raw_items.append((
                score,
                {
                    "id": chunk.id,
                    "policy_id": policy.id,
                    "title": policy.title,
                    "category": policy.category,
                    "section": chunk.section,
                    "page_number": chunk.page_number,
                    "content": chunk.content,
                    "citation": f"{policy.title} (Page {chunk.page_number}, {chunk.section})"
                }
            ))

        raw_items.sort(key=lambda x: x[0], reverse=True)
        items = [item for _, item in raw_items[:limit]]

        # If no items found, ensure all standard policies are seeded and re-query once
        if not items:
            c_count = (await db.execute(
                select(func.count(PolicyChunk.id)).select_from(PolicyChunk).join(Policy).where(Policy.organization_id == organization_id)
            )).scalar() or 0
            if c_count < 9:
                from app.core.policy_generator import seed_policies_if_needed
                await seed_policies_if_needed(db, organization_id)
                re_results = await db.execute(stmt)
                for chunk, policy in re_results.all():
                    items.append({
                        "id": chunk.id,
                        "policy_id": policy.id,
                        "title": policy.title,
                        "category": policy.category,
                        "section": chunk.section,
                        "page_number": chunk.page_number,
                        "content": chunk.content,
                        "citation": f"{policy.title} (Page {chunk.page_number}, {chunk.section})"
                    })

        return items
