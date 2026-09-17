"""Tests for Zenith Repository Intelligence Engine:
- Dependency Graph & Blast Radius
- Static Call Graph & Execution Paths
- Automated Test Mapping
- Semantic Code Search
- Architecture Understanding
- Hierarchical Context Management
"""
import pytest
from pathlib import Path

from zenith.tools.repo_intelligence import (
    analyze_dependency_graph,
    call_graph,
    map_tests,
    semantic_code_search,
    analyze_architecture,
    get_hierarchical_context,
    RepositoryDependencyGraph,
    CallGraphEngine,
    TestMapper,
    SemanticCodeSearchEngine,
)


@pytest.fixture
def sample_codebase(tmp_path: Path):
    """Create a mock repository with API -> Service -> Store -> DB layers."""
    workspace = tmp_path / "mock_project"
    workspace.mkdir()

    # 1. Database schema / store
    db_file = workspace / "store.py"
    db_file.write_text("""
\"\"\"Persistent SQLite store and database migrations.\"\"\"
class MemoryStore:
    def init_db(self):
        query = "CREATE TABLE IF NOT EXISTS memories (id TEXT, text TEXT)"
        return query

    def get_user(self, user_id: str):
        return {"id": user_id, "name": "Aditya"}
""")

    # 2. Service layer
    svc_file = workspace / "service.py"
    svc_file.write_text("""
\"\"\"User business logic service.\"\"\"
from store import MemoryStore

class UserService:
    def __init__(self):
        self.store = MemoryStore()

    def get_profile(self, user_id: str):
        return self.store.get_user(user_id)
""")

    # 3. API endpoint layer
    api_file = workspace / "main.py"
    api_file.write_text("""
\"\"\"FastAPI application entrypoint.\"\"\"
from service import UserService

svc = UserService()

def get_user_endpoint(user_id: str):
    \"\"\"Authenticate and retrieve user profile.\"\"\"
    return svc.get_profile(user_id)
""")

    # 4. Tests
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_auth.py"
    test_file.write_text("""
\"\"\"Tests for authentication and user store.\"\"\"
def test_get_user():
    from store import MemoryStore
    store = MemoryStore()
    user = store.get_user("u123")
    assert user["name"] == "Aditya"

def test_user_service():
    from service import UserService
    s = UserService()
    res = s.get_profile("u123")
    assert res is not None
""")

    # 5. requirements.txt
    req_file = workspace / "requirements.txt"
    req_file.write_text("fastapi>=0.110.0\nuvicorn>=0.28.0\npytest>=8.0.0\n")

    return workspace


@pytest.mark.anyio
async def test_dependency_graph_and_blast_radius(sample_codebase: Path):
    # Overall architecture
    overview = await analyze_dependency_graph(repo_path=str(sample_codebase))
    assert "Repository Dependency Architecture Overview" in overview

    # Target blast radius for MemoryStore
    blast = await analyze_dependency_graph(target="MemoryStore", repo_path=str(sample_codebase))
    assert "Dependency & Blast-Radius Analysis" in blast
    assert "MemoryStore" in blast
    assert "Risk Level" in blast
    assert "Architectural Dependency Flow" in blast


@pytest.mark.anyio
async def test_call_graph_execution_paths(sample_codebase: Path):
    # Incoming calls to get_user
    res = await call_graph("get_user", repo_path=str(sample_codebase), direction="incoming")
    assert "Static Call Graph for `get_user`" in res
    assert "Direct Callers" in res
    assert "get_profile" in res or "test_get_user" in res

    # Outgoing calls
    res_out = await call_graph("get_profile", repo_path=str(sample_codebase), direction="outgoing")
    assert "Outgoing Invocations" in res_out
    assert "get_user" in res_out


@pytest.mark.anyio
async def test_automated_test_mapping(sample_codebase: Path):
    # Target function get_user
    map_res = await map_tests("get_user", repo_path=str(sample_codebase))
    assert "Test Mapping for `get_user`" in map_res
    assert "test_auth.py" in map_res
    assert "test_get_user" in map_res
    assert "pytest" in map_res


@pytest.mark.anyio
async def test_semantic_code_search(sample_codebase: Path):
    # Conceptual search for authentication
    res = await semantic_code_search("Where is user profile retrieved?", repo_path=str(sample_codebase))
    assert "Semantic Code Search Results" in res
    assert "get_profile" in res or "get_user" in res

    # Conceptual search for database persistence
    db_res = await semantic_code_search("database store table persistence", repo_path=str(sample_codebase))
    assert "MemoryStore" in db_res or "store.py" in db_res


@pytest.mark.anyio
async def test_architecture_understanding(sample_codebase: Path):
    arch = await analyze_architecture(repo_path=str(sample_codebase))
    assert "Repository Architecture Map" in arch
    assert "main.py" in arch
    assert "UserService" in arch
    assert "MemoryStore" in arch
    assert "fastapi" in arch


@pytest.mark.anyio
async def test_hierarchical_context_tiers(sample_codebase: Path):
    # Tier 0 Macro
    ctx0 = await get_hierarchical_context("refactor user store", depth="0", repo_path=str(sample_codebase))
    assert "Tier 0: Project Memory" in ctx0
    assert "Tier 1" not in ctx0

    # Tier 1 Subsystem
    ctx1 = await get_hierarchical_context("refactor user store", subsystem="swe_engine", depth="1", repo_path=str(sample_codebase))
    assert "Tier 0" in ctx1
    assert "Tier 1: Active Subsystem Context (`swe_engine`)" in ctx1
    assert "Tier 2" not in ctx1

    # Tier 3 Full Deep Context
    ctx3 = await get_hierarchical_context("how is get_user called?", depth="3", repo_path=str(sample_codebase))
    assert "Tier 0" in ctx3
    assert "Tier 1" in ctx3
    assert "Tier 2" in ctx3
    assert "Tier 3: Deep Verification & Call Paths" in ctx3
