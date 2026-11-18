import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_all_four_corporate_policies_seeded_and_functional():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Login as admin
        login_res = await ac.post("/api/v1/auth/login", json={
            "email": "admin@attendai.com",
            "password": "Admin@123"
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. List policies - must contain all 4 standard policies
        res = await ac.get("/api/v1/policies", headers=headers)
        assert res.status_code == 200
        policies = res.json()
        assert len(policies) >= 4

        titles = [p["title"] for p in policies]
        expected_titles = [
            "AttendAI Global Attendance and Working Hours Policy",
            "Comprehensive Leave and Time-Off Guidelines",
            "Remote Work Guidelines 2026",
            "Workplace Code of Conduct"
        ]
        for exp in expected_titles:
            assert exp in titles, f"Missing expected policy: {exp}"

        # 3. Test Detail, Content, View, and Download for each of the 4 policies
        for exp in expected_titles:
            pol = next(p for p in policies if p["title"] == exp)
            pid = pol["id"]

            # Detail
            det_res = await ac.get(f"/api/v1/policies/{pid}", headers=headers)
            assert det_res.status_code == 200
            det = det_res.json()
            assert det["has_physical_file"] is True
            assert det["chunk_count"] >= 1

            # Content
            content_res = await ac.get(f"/api/v1/policies/{pid}/content", headers=headers)
            assert content_res.status_code == 200
            c_data = content_res.json()
            assert c_data["elements_count"] > 0
            if exp == "Workplace Code of Conduct":
                assert c_data["format"] == "docx"
                types = [el["type"] for el in c_data["elements"]]
                assert "heading1" in types or "paragraph" in types
            else:
                assert c_data["format"] == "pdf"
                assert c_data["total_pages"] >= 1

            # View
            view_res = await ac.get(f"/api/v1/policies/{pid}/view", headers=headers)
            assert view_res.status_code == 200
            if exp == "Workplace Code of Conduct":
                assert "officedocument" in view_res.headers.get("content-type", "")
            else:
                assert view_res.headers.get("content-type") == "application/pdf"
            assert len(view_res.content) > 1000

            # Download
            dl_res = await ac.get(f"/api/v1/policies/{pid}/download", headers=headers)
            assert dl_res.status_code == 200
            assert "attachment" in dl_res.headers.get("content-disposition", "")
            assert len(dl_res.content) > 1000

        # 4. Search across all 4 policies
        queries = ["overtime", "annual leave", "remote", "harassment"]
        for q in queries:
            s_res = await ac.get(f"/api/v1/policies/search?query={q}", headers=headers)
            assert s_res.status_code == 200
            results = s_res.json()
            assert len(results) > 0, f"Search for '{q}' returned no results"
