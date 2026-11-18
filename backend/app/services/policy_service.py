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
        """Extract pages from PDF using PyMuPDF."""
        pages = []
        try:
            import pymupdf as fitz
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_content = page.get_text()
                if text_content.strip():
                    pages.append({
                        "page_number": page_num + 1,
                        "content": text_content.strip()
                    })
            doc.close()
        except Exception as e:
            raise ValidationException(f"Failed to extract text from PDF: {str(e)}")
        return pages

    @staticmethod
    def extract_text_from_docx(file_path: str) -> List[Dict[str, Any]]:
        """Extract sections from DOCX using python-docx."""
        pages = []
        try:
            import docx
            doc = docx.Document(file_path)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            if full_text.strip():
                # Split roughly every 1500 chars to simulate pages/sections
                chunks = [full_text[i:i+1500] for i in range(0, len(full_text), 1500)]
                for idx, c in enumerate(chunks):
                    pages.append({
                        "page_number": idx + 1,
                        "content": c.strip()
                    })
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
        if ext == ".pdf":
            extracted = PolicyService.extract_text_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            extracted = PolicyService.extract_text_from_docx(file_path)
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            extracted = [{"page_number": 1, "content": content}]
        else:
            raise ValidationException(f"Unsupported file format: {ext}. Only PDF, DOCX, and TXT are supported.")

        policy = Policy(
            organization_id=organization_id,
            title=title,
            category=category,
            file_path=file_path,
            file_size=file_size,
            status="active"
        )
        db.add(policy)
        await db.flush()

        for item in extracted:
            chunk = PolicyChunk(
                policy_id=policy.id,
                title=title,
                section=f"Section {item['page_number']}",
                page_number=item["page_number"],
                content=item["content"],
                token_count=len(item["content"].split())
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

        stmt = stmt.limit(limit)
        results = await db.execute(stmt)
        
        items = []
        for chunk, policy in results.all():
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
