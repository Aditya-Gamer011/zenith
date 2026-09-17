"""Zenith Repository Intelligence Engine — Deep Codebase Comprehension,
Dependency Blast-Radius Analysis, Static Call Graphs, Test Mapping,
Semantic Code Search, Architecture Understanding, and Hierarchical Context.

Elevates Zenith's SWE capabilities far beyond simple symbol lookup:
1. Dependency Graph:
   - Traces API Endpoint -> Service -> Repository -> Database models.
   - Computes blast radius and affected components when code is modified.
2. Static Call Graph & Reachability:
   - Identifies what execution paths reach a given function (reverse call graph).
   - Maps callers, entry points, and downstream callee chains.
3. Automated Test Mapping:
   - Maps modified functions or files directly to covering test files and test cases.
   - Generates exact targeted pytest execution commands.
4. Semantic Code Search:
   - Natural language concept retrieval across docstrings, comments, endpoints, and symbol names.
   - Synonym and conceptual query expansion (e.g. "Where is authentication handled?").
5. Architectural Map:
   - Auto-discovers and maintains entry points, services, database models, APIs, and dependencies.
6. Hierarchical Context Management:
   - Progressive disclosure: Project Memory -> Subsystem -> Interface Skeletons -> Deep Task Context.
   - Prevents context window saturation during long-horizon coding tasks.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build",
    ".zenith_checkpoints", ".cache", ".idea", ".vscode", "coverage",
    ".tox", "eggs", "*.egg-info", "site-packages",
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".mp3", ".mp4",
    ".woff", ".woff2", ".ttf", ".eot", ".bin", ".lock",
}


def _resolve_workspace(repo_path: str = "") -> Path:
    """Resolve target repository/workspace path."""
    if repo_path and repo_path.strip():
        p = Path(repo_path.strip()).expanduser().resolve()
        if p.is_dir():
            return p
    if settings.workspace_dir and settings.workspace_dir.exists():
        return settings.workspace_dir.resolve()
    return Path.cwd().resolve()

log = logging.getLogger("zenith.repo_intelligence")

# ─── Semantic Synonym & Concept Expansion Dictionary ─────────────────────────
CONCEPT_EXPANSIONS: dict[str, list[str]] = {
    "auth": ["authenticate", "authentication", "login", "jwt", "token", "bearer", "password", "oauth", "credential", "session"],
    "authentication": ["auth", "login", "jwt", "token", "bearer", "password", "oauth", "credential", "session", "user"],
    "database": ["db", "sqlite", "table", "store", "query", "schema", "model", "persist", "sql", "migration"],
    "db": ["database", "sqlite", "table", "store", "query", "schema", "model", "persist", "sql"],
    "api": ["endpoint", "route", "router", "fastapi", "http", "request", "response", "get", "post", "payload"],
    "test": ["pytest", "assert", "fixture", "mock", "testcase", "check", "verify", "suite"],
    "memory": ["mem0", "blackboard", "recall", "store", "timeline", "preference", "fact", "long_term"],
    "media": ["video", "audio", "audiogram", "slideshow", "ffmpeg", "transcode", "stream", "image", "tts"],
    "video": ["media", "mp4", "webm", "slideshow", "audiogram", "ffmpeg", "overlay", "subtitles"],
    "audio": ["sound", "speech", "tts", "whisper", "voice", "mp3", "wav", "loudnorm", "audiogram"],
    "worker": ["peacant", "antigravity", "daemon", "agent_submit", "task", "background", "subprocess"],
    "sandbox": ["security", "jail", "protection", "safe", "permission", "restricted", "isolation"],
    "patch": ["diff", "transaction", "rollback", "edit", "apply", "checkpoint", "chunk", "ast"],
    "search": ["find", "grep", "lookup", "query", "index", "semantic", "ast"],
}


# ─── 1. Dependency Graph & Blast-Radius Engine ───────────────────────────────
@dataclass
class ComponentNode:
    name: str
    kind: str  # ENDPOINT, SERVICE, REPOSITORY, DATABASE, UTILITY, TEST
    file_path: str
    line: int
    dependencies: list[str] = field(default_factory=list)  # downstream
    dependents: list[str] = field(default_factory=list)    # upstream callers


class RepositoryDependencyGraph:
    """Extracts component tiers (Endpoint -> Service -> Repository -> Database) and computes blast radius."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.nodes: dict[str, ComponentNode] = {}
        self.routes: list[dict[str, Any]] = []
        self.db_tables: set[str] = set()

    def build(self) -> None:
        """Scan workspace ASTs and discover architectural tiers."""
        for py_path in self.workspace.rglob("*.py"):
            rel_parts = py_path.relative_to(self.workspace).parts
            if any(part in IGNORE_DIRS or part.startswith(".") for part in rel_parts):
                continue
            self._analyze_file(py_path)

        # Cross-link upstream dependents
        for name, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in self.nodes:
                    if name not in self.nodes[dep].dependents:
                        self.nodes[dep].dependents.append(name)

    def _analyze_file(self, py_path: Path) -> None:
        rel_str = str(py_path.relative_to(self.workspace)).replace("\\", "/")
        try:
            content = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=py_path.name)
        except Exception:
            return

        # Check for DB table creation or schemas
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", content, re.IGNORECASE):
            self.db_tables.add(m.group(1))

        # Classify nodes based on AST
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for FastAPI / Starlette routes
                for dec in node.decorator_list:
                    dec_src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                    if any(verb in dec_src for verb in (".get(", ".post(", ".put(", ".delete(", ".websocket(")):
                        route_name = f"ENDPOINT:{node.name} ({rel_str}:{node.lineno})"
                        comp = ComponentNode(
                            name=route_name,
                            kind="ENDPOINT",
                            file_path=rel_str,
                            line=node.lineno,
                        )
                        # Extract called services or functions
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                                comp.dependencies.append(sub.func.id)
                            elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                                comp.dependencies.append(sub.func.attr)
                        self.nodes[route_name] = comp

            elif isinstance(node, ast.ClassDef):
                c_name = node.name.lower()
                kind = "UTILITY"
                if any(k in c_name for k in ("store", "repo", "db", "database")):
                    kind = "REPOSITORY"
                elif any(k in c_name for k in ("service", "manager", "orchestrator", "engine")):
                    kind = "SERVICE"
                elif any(k in c_name for k in ("model", "schema", "table")):
                    kind = "DATABASE"

                node_id = f"{kind}:{node.name}"
                comp = ComponentNode(
                    name=node_id,
                    kind=kind,
                    file_path=rel_str,
                    line=node.lineno,
                )
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        comp.dependencies.append(sub.func.id)
                    elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        comp.dependencies.append(sub.func.attr)
                self.nodes[node_id] = comp

    def get_blast_radius(self, target: str) -> dict[str, Any]:
        """Compute the upstream and downstream blast radius when modifying target."""
        target_clean = target.strip().lower()
        matched_keys = [k for k in self.nodes if target_clean in k.lower()]

        if not matched_keys:
            # Check loose match in file paths
            matched_keys = [k for k, node in self.nodes.items() if target_clean in node.file_path.lower()]

        affected_up: Set[str] = set()
        affected_down: Set[str] = set()

        for k in matched_keys:
            # Walk upstream (who calls this?)
            queue = deque([k])
            while queue:
                curr = queue.popleft()
                if curr in self.nodes:
                    for up in self.nodes[curr].dependents:
                        if up not in affected_up:
                            affected_up.add(up)
                            queue.append(up)

            # Walk downstream (what does this call?)
            queue = deque([k])
            while queue:
                curr = queue.popleft()
                if curr in self.nodes:
                    for down in self.nodes[curr].dependencies:
                        if down in self.nodes and down not in affected_down:
                            affected_down.add(down)
                            queue.append(down)

        endpoints = [x for x in affected_up if "ENDPOINT:" in x]
        services = [x for x in (affected_up | affected_down) if "SERVICE:" in x]
        repos = [x for x in (affected_up | affected_down) if "REPOSITORY:" in x]

        risk = "LOW"
        if len(endpoints) > 2 or len(services) > 3:
            risk = "HIGH"
        elif endpoints or services:
            risk = "MEDIUM"

        return {
            "target": target,
            "matched_components": matched_keys,
            "risk_level": risk,
            "impacted_endpoints": endpoints,
            "impacted_services": services,
            "impacted_repositories": repos,
            "total_impacted_nodes": len(affected_up | affected_down),
            "upstream_dependents": list(affected_up),
            "downstream_dependencies": list(affected_down),
        }


async def analyze_dependency_graph(target: str = "", repo_path: str = "") -> str:
    """Analyze the full dependency chain and blast radius for an API endpoint, service, or repository.
    
    Traces: API Endpoint -> Service -> Repository -> Database Table.
    """
    workspace = _resolve_workspace(repo_path)
    graph = RepositoryDependencyGraph(workspace)
    graph.build()

    if not target or not target.strip():
        # General architectural dependency overview
        endpoints = [k for k, v in graph.nodes.items() if v.kind == "ENDPOINT"]
        services = [k for k, v in graph.nodes.items() if v.kind == "SERVICE"]
        repos = [k for k, v in graph.nodes.items() if v.kind == "REPOSITORY"]
        return (
            f"📊 **Repository Dependency Architecture Overview** ({workspace.name}):\n"
            f"- **Discovered Endpoints** ({len(endpoints)}): {', '.join([e.split(' ')[0] for e in endpoints[:5]])}...\n"
            f"- **Discovered Services** ({len(services)}): {', '.join([s.split(':')[1] for s in services[:5]])}...\n"
            f"- **Discovered Repositories/Stores** ({len(repos)}): {', '.join([r.split(':')[1] for r in repos[:5]])}...\n"
            f"- **Known Database Tables** ({len(graph.db_tables)}): {', '.join(sorted(graph.db_tables)[:8])}\n\n"
            f"💡 *Specify a target (e.g. `analyze_dependency_graph(target='MemoryStore')`) to compute exact blast radius and impact chains.*"
        )

    blast = graph.get_blast_radius(target)
    lines = [
        f"🎯 **Dependency & Blast-Radius Analysis for `{target}`**:",
        f"- **Risk Level**: `{blast['risk_level']}` ({blast['total_impacted_nodes']} total affected components)",
    ]

    if blast["matched_components"]:
        lines.append(f"- **Matched Architectural Nodes**: {', '.join(blast['matched_components'])}")

    if blast["impacted_endpoints"]:
        lines.append(f"\n🌐 **Affected API Endpoints (Upstream Invocations)**:")
        for ep in blast["impacted_endpoints"]:
            lines.append(f"  • `{ep}`")

    if blast["impacted_services"]:
        lines.append(f"\n⚙️ **Affected Services & Orchestrators**:")
        for s in blast["impacted_services"]:
            lines.append(f"  • `{s}`")

    if blast["impacted_repositories"]:
        lines.append(f"\n🗄️ **Affected Data Stores & Repositories**:")
        for r in blast["impacted_repositories"]:
            lines.append(f"  • `{r}`")

    # Dependency Flow visualization
    lines.append(f"\n🧩 **Architectural Dependency Flow**:")
    lines.append(f"```text")
    lines.append(f"API Endpoints (FastAPI)")
    lines.append(f"   ↓ (dispatches to)")
    lines.append(f"Services & Agents (AgentService / Orchestrator)")
    lines.append(f"   ↓ (queries/mutates)")
    lines.append(f"Repositories & Adapters (MemoryStore / SQLite / Blackboard)")
    lines.append(f"   ↓ (persists in)")
    lines.append(f"Database Tables ({', '.join(list(graph.db_tables)[:5]) or 'sqlite.db'})")
    lines.append(f"```")

    return "\n".join(lines)


# ─── 2. Static Call Graph & Execution Paths ──────────────────────────────────
@dataclass
class CallSite:
    caller_function: str
    caller_file: str
    line: int
    code_snippet: str = ""


class CallGraphEngine:
    """Builds reverse call graphs to show execution paths reaching a function."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        # callee_name -> list of CallSite
        self.incoming_calls: dict[str, list[CallSite]] = defaultdict(list)
        # caller_name -> list of callee_names
        self.outgoing_calls: dict[str, list[str]] = defaultdict(list)
        # function_name -> (file, line)
        self.definitions: dict[str, tuple[str, int]] = {}

    def build(self) -> None:
        """Parse all Python files to extract function calls."""
        for py_path in self.workspace.rglob("*.py"):
            rel_parts = py_path.relative_to(self.workspace).parts
            if any(part in IGNORE_DIRS or part.startswith(".") for part in rel_parts):
                continue
            self._parse_file_calls(py_path)

    def _parse_file_calls(self, py_path: Path) -> None:
        rel_str = str(py_path.relative_to(self.workspace)).replace("\\", "/")
        try:
            content = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=py_path.name)
            lines = content.splitlines()
        except Exception:
            return

        class CallVisitor(ast.NodeVisitor):
            def __init__(self, engine: CallGraphEngine):
                self.engine = engine
                self.current_func = "<module>"

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                old_func = self.current_func
                self.current_func = node.name
                self.engine.definitions[node.name] = (rel_str, node.lineno)
                self.generic_visit(node)
                self.current_func = old_func

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                old_func = self.current_func
                self.current_func = node.name
                self.engine.definitions[node.name] = (rel_str, node.lineno)
                self.generic_visit(node)
                self.current_func = old_func

            def visit_Call(self, node: ast.Call) -> None:
                callee = ""
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    callee = node.func.attr

                if callee:
                    snippet = lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else ""
                    call_site = CallSite(
                        caller_function=self.current_func,
                        caller_file=rel_str,
                        line=node.lineno,
                        code_snippet=snippet,
                    )
                    self.engine.incoming_calls[callee].append(call_site)
                    self.engine.outgoing_calls[self.current_func].append(callee)
                self.generic_visit(node)

        visitor = CallVisitor(self)
        visitor.visit(tree)

    def find_execution_paths(self, target_func: str, max_depth: int = 4) -> list[list[str]]:
        """Find execution paths that reach target_func."""
        paths: list[list[str]] = []

        def dfs(current: str, current_path: list[str], visited: set[str], depth: int) -> None:
            if depth > max_depth:
                return
            callers = self.incoming_calls.get(current, [])
            if not callers:
                if len(current_path) > 1:
                    paths.append(list(reversed(current_path)))
                return

            for cs in callers:
                c_name = cs.caller_function
                if c_name in visited or c_name == current:
                    continue
                visited.add(c_name)
                current_path.append(f"{cs.caller_file}:{cs.line} ({c_name})")
                dfs(c_name, current_path, visited, depth + 1)
                current_path.pop()
                visited.remove(c_name)

        dfs(target_func, [target_func], {target_func}, 1)
        return paths[:10]


async def call_graph(
    function_name: str,
    repo_path: str = "",
    direction: str = "incoming",
    max_depth: int = 4,
) -> str:
    """Build static call graph and execution paths reaching a function.
    
    Args:
        function_name: Name of target function or method.
        repo_path: Root of workspace.
        direction: 'incoming' (what reaches this function?) or 'outgoing' (what does it call?).
        max_depth: Maximum execution path depth.
    """
    if not function_name or not function_name.strip():
        return "[call_graph error] Must provide `function_name`."

    workspace = _resolve_workspace(repo_path)
    engine = CallGraphEngine(workspace)
    engine.build()

    target = function_name.strip()
    out = [f"📈 **Static Call Graph for `{target}`** ({direction} flow):"]

    if target in engine.definitions:
        def_file, def_line = engine.definitions[target]
        out.append(f"📍 **Defined At**: `{def_file}:{def_line}`\n")
    else:
        out.append(f"⚠️ *Symbol definition not found locally, inspecting external/caller references...*\n")

    if direction == "incoming":
        direct_callers = engine.incoming_calls.get(target, [])
        out.append(f"📞 **Direct Callers** ({len(direct_callers)} call sites):")
        if not direct_callers:
            out.append(f"  *(No direct callers found in workspace Python files. May be an entry point, API route, or test fixture.)*")
        else:
            for cs in direct_callers[:8]:
                out.append(f"  • `{cs.caller_file}:{cs.line}` inside `{cs.caller_function}()`\n    `{cs.code_snippet}`")

        # Execution Paths
        paths = engine.find_execution_paths(target, max_depth=max_depth)
        if paths:
            out.append(f"\n🛤️ **Execution Paths Reaching `{target}`** ({len(paths)} paths discovered):")
            for idx, p in enumerate(paths, 1):
                path_str = " ➔ ".join(p)
                out.append(f"  {idx}. {path_str} ➔ `{target}()`")

    else:
        callees = engine.outgoing_calls.get(target, [])
        out.append(f"Outgoing Invocations ({len(callees)} calls):")
        for c in set(callees):
            out.append(f"  • Calls `{c}()`")

    return "\n".join(out)


# ─── 3. Automated Test Mapping ───────────────────────────────────────────────
@dataclass
class TestMappingResult:
    target: str
    matching_test_files: list[str]
    matching_test_cases: list[dict[str, Any]]
    suggested_command: str


class TestMapper:
    """Maps modified functions, classes, or files to covering test suites."""

    __test__ = False

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.test_files: list[Path] = []

    def discover_tests(self) -> None:
        """Find test files in workspace."""
        for p in self.workspace.rglob("*.py"):
            rel_parts = p.relative_to(self.workspace).parts
            if any(part in IGNORE_DIRS or part.startswith(".") for part in rel_parts):
                continue
            name = p.name.lower()
            if name.startswith("test_") or name.endswith("_test.py") or "tests" in rel_parts:
                self.test_files.append(p)

    def map_target(self, target: str) -> TestMappingResult:
        """Find test cases and files relevant to target symbol or file."""
        self.discover_tests()
        clean_target = target.strip()
        stem = Path(clean_target).stem.replace("test_", "")

        matched_files: Set[str] = set()
        matched_cases: list[dict[str, Any]] = []

        for tf in self.test_files:
            rel_str = str(tf.relative_to(self.workspace)).replace("\\", "/")
            # 1. Filename heuristic
            if stem.lower() in tf.name.lower():
                matched_files.add(rel_str)

            # 2. Content / AST scan
            try:
                content = tf.read_text(encoding="utf-8", errors="replace")
                if clean_target in content or stem in content:
                    matched_files.add(rel_str)
                    tree = ast.parse(content, filename=tf.name)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if node.name.startswith("test_"):
                                func_src = ast.get_source_segment(content, node) or ""
                                if clean_target in func_src or clean_target in node.name:
                                    matched_cases.append({
                                        "file": rel_str,
                                        "test_name": node.name,
                                        "line": node.lineno,
                                    })
            except Exception:
                continue

        suggested_cmd = ""
        if matched_cases:
            top = matched_cases[0]
            suggested_cmd = f".venv/bin/pytest {top['file']} -k {top['test_name']}"
        elif matched_files:
            suggested_cmd = f".venv/bin/pytest {list(matched_files)[0]}"
        else:
            suggested_cmd = f".venv/bin/pytest -k {clean_target}"

        return TestMappingResult(
            target=clean_target,
            matching_test_files=sorted(matched_files),
            matching_test_cases=matched_cases[:10],
            suggested_command=suggested_cmd,
        )


async def map_tests(target: str, repo_path: str = "") -> str:
    """Automatically identify relevant test files and test cases for a modified function or file.
    
    Args:
        target: Function name, class name, or relative file path (e.g. `authenticate`, `apply_patch_transaction`, `store.py`).
        repo_path: Workspace path.
    """
    if not target or not target.strip():
        return "[map_tests error] Must provide target function, class, or file."

    workspace = _resolve_workspace(repo_path)
    mapper = TestMapper(workspace)
    res = mapper.map_target(target)

    out = [
        f"🧪 **Test Mapping for `{res.target}`**:",
        f"- **Covering Test Files** ({len(res.matching_test_files)} files):",
    ]
    if not res.matching_test_files:
        out.append(f"  *(No specific test files matched. Recommended: full suite run)*")
    else:
        for f in res.matching_test_files:
            out.append(f"  • `{f}`")

    if res.matching_test_cases:
        out.append(f"\n🎯 **Targeted Test Cases** ({len(res.matching_test_cases)}):")
        for tc in res.matching_test_cases:
            out.append(f"  • `{tc['file']}::{tc['test_name']}` (line {tc['line']})")

    out.append(f"\n⚡ **Suggested Verification Command**:")
    out.append(f"```bash\n{res.suggested_command}\n```")
    return "\n".join(out)


# ─── 4. Semantic Code Search ─────────────────────────────────────────────────
@dataclass
class CodeChunk:
    file_path: str
    line_number: int
    symbol_name: str
    kind: str  # function, class, endpoint, docstring
    text: str
    docstring: str = ""


class SemanticCodeSearchEngine:
    """Natural-language semantic retrieval across codebase docstrings, signatures, and concepts."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.chunks: list[CodeChunk] = []

    def index(self) -> None:
        """Extract searchable semantic chunks from codebase."""
        for py_path in self.workspace.rglob("*.py"):
            rel_parts = py_path.relative_to(self.workspace).parts
            if any(part in IGNORE_DIRS or part.startswith(".") for part in rel_parts):
                continue
            self._extract_chunks(py_path)

    def _extract_chunks(self, py_path: Path) -> None:
        rel_str = str(py_path.relative_to(self.workspace)).replace("\\", "/")
        try:
            content = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=py_path.name)
        except Exception:
            return

        # Module docstring
        mod_doc = ast.get_docstring(tree) or ""
        if mod_doc:
            self.chunks.append(CodeChunk(
                file_path=rel_str,
                line_number=1,
                symbol_name=py_path.name,
                kind="module_overview",
                text=f"{py_path.name} module {mod_doc}",
                docstring=mod_doc,
            ))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node) or ""
                self.chunks.append(CodeChunk(
                    file_path=rel_str,
                    line_number=node.lineno,
                    symbol_name=node.name,
                    kind="function",
                    text=f"{node.name} {' '.join(a.arg for a in node.args.args)} {doc}",
                    docstring=doc,
                ))
            elif isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                self.chunks.append(CodeChunk(
                    file_path=rel_str,
                    line_number=node.lineno,
                    symbol_name=node.name,
                    kind="class",
                    text=f"{node.name} {doc}",
                    docstring=doc,
                ))

    def search(self, query: str, top_k: int = 8) -> list[tuple[CodeChunk, float]]:
        """Perform semantic concept scoring with expanded query terms."""
        clean_q = query.lower()
        tokens = re.findall(r"[a-z0-9_]+", clean_q)

        # Expand query with conceptual synonyms
        expanded_tokens = set(tokens)
        for t in tokens:
            if t in CONCEPT_EXPANSIONS:
                expanded_tokens.update(CONCEPT_EXPANSIONS[t])

        scored: list[tuple[CodeChunk, float]] = []

        for chunk in self.chunks:
            chunk_low = chunk.text.lower()
            sym_low = chunk.symbol_name.lower()
            file_low = chunk.file_path.lower()

            score = 0.0
            for term in expanded_tokens:
                # Direct symbol name match
                if term in sym_low:
                    score += 5.0
                # Direct file path match
                if term in file_low:
                    score += 3.0
                # Docstring match
                if chunk.docstring and term in chunk.docstring.lower():
                    score += 4.0
                # General body/arg match
                if term in chunk_low:
                    score += 1.5

            # Phrase match bonus
            if clean_q in chunk_low:
                score += 10.0

            if score > 0:
                scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


async def semantic_code_search(query: str, repo_path: str = "", max_results: int = 8) -> str:
    """Semantic conceptual code search (e.g. 'Where is authentication handled?', 'rate limiting').
    
    Args:
        query: Natural-language query describing the function, concept, or feature.
        repo_path: Workspace directory.
        max_results: Max results to return.
    """
    if not query or not query.strip():
        return "[semantic_code_search error] Query is required."

    workspace = _resolve_workspace(repo_path)
    engine = SemanticCodeSearchEngine(workspace)
    engine.index()
    results = engine.search(query, top_k=max_results)

    if not results:
        return f"🔍 **Semantic Search for `{query}`**: No matches found in codebase."

    out = [f"🔍 **Semantic Code Search Results for `{query}`** ({len(results)} matches):"]
    for idx, (chunk, score) in enumerate(results, 1):
        doc_preview = chunk.docstring.strip().splitlines()[0] if chunk.docstring else "No docstring provided"
        out.append(
            f"{idx}. `{chunk.file_path}:{chunk.line_number}` [{chunk.kind}: `{chunk.symbol_name}`] "
            f"(Score: {score:.1f})\n"
            f"   💬 *{doc_preview[:140]}*"
        )

    return "\n".join(out)


# ─── 5. Architecture Understanding & Self-Maintaining Map ────────────────────
@dataclass
class ArchitectureMap:
    entry_points: list[str]
    modules: dict[str, list[str]]
    services: list[str]
    database_models: list[str]
    api_endpoints: list[str]
    dependencies: list[str]
    tests_summary: str


class ArchitectureAnalyzer:
    """Constructs and maintains high-level system architecture."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def analyze(self) -> ArchitectureMap:
        entry_points: list[str] = []
        modules: dict[str, list[str]] = defaultdict(list)
        services: list[str] = []
        db_models: list[str] = []
        endpoints: list[str] = []
        deps: list[str] = []

        # 1. Discovered entry points
        for candidate in ("run.py", "main.py", "server.py", "app.py", "worker/peacant.py"):
            if (self.workspace / candidate).is_file():
                entry_points.append(candidate)

        # 2. Dependencies
        req_file = self.workspace / "requirements.txt"
        if req_file.is_file():
            try:
                for line in req_file.read_text().splitlines():
                    clean = line.strip().split("==")[0].split(">=")[0]
                    if clean and not clean.startswith("#"):
                        deps.append(clean)
            except Exception:
                pass

        # 3. Codebase AST inspection
        for py_path in self.workspace.rglob("*.py"):
            rel_parts = py_path.relative_to(self.workspace).parts
            if any(part in IGNORE_DIRS or part.startswith(".") for part in rel_parts):
                continue
            rel_str = str(py_path.relative_to(self.workspace)).replace("\\", "/")
            domain = rel_parts[0] if len(rel_parts) > 1 else "root"
            modules[domain].append(py_path.name)

            try:
                content = py_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=py_path.name)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for dec in node.decorator_list:
                            dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                            if any(v in dec_str for v in (".get(", ".post(", ".put(", ".delete(")):
                                endpoints.append(f"{node.name} ({rel_str})")
                    elif isinstance(node, ast.ClassDef):
                        c_name = node.name.lower()
                        if any(k in c_name for k in ("service", "manager", "orchestrator", "engine")):
                            services.append(f"{node.name} ({rel_str})")
                        elif any(k in c_name for k in ("store", "model", "schema", "table")):
                            db_models.append(f"{node.name} ({rel_str})")
            except Exception:
                continue

        # 4. Tests summary
        test_files = list(self.workspace.glob("tests/test_*.py"))

        return ArchitectureMap(
            entry_points=entry_points,
            modules={k: v[:6] for k, v in modules.items()},
            services=services[:12],
            database_models=db_models[:12],
            api_endpoints=endpoints[:15],
            dependencies=deps[:15],
            tests_summary=f"{len(test_files)} dedicated test suites in `tests/`",
        )


async def analyze_architecture(repo_path: str = "") -> str:
    """Automatically construct and maintain repository architectural map.
    
    Maps: Entry points, services, modules, database models, APIs, and dependencies.
    """
    workspace = _resolve_workspace(repo_path)
    analyzer = ArchitectureAnalyzer(workspace)
    arch = analyzer.analyze()

    out = [
        f"🏛️ **Repository Architecture Map** (`{workspace.name}`):",
        f"\n🚀 **Core Entry Points**:",
    ]
    for ep in arch.entry_points:
        out.append(f"  • `{ep}`")

    out.append(f"\n📦 **Architectural Modules & Packages**:")
    for mod, files in arch.modules.items():
        out.append(f"  • `{mod}/`: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}")

    out.append(f"\n⚙️ **Core Services & Orchestration Layer** ({len(arch.services)} services):")
    for s in arch.services:
        out.append(f"  • `{s}`")

    out.append(f"\n🗄️ **Database & Persistence Tier** ({len(arch.database_models)} models/stores):")
    for db in arch.database_models:
        out.append(f"  • `{db}`")

    out.append(f"\n🌐 **Discovered API Endpoints** ({len(arch.api_endpoints)} routes):")
    for route in arch.api_endpoints:
        out.append(f"  • `{route}`")

    out.append(f"\n🧪 **Test & Verification Infrastructure**: {arch.tests_summary}")
    out.append(f"📚 **Key External Dependencies**: {', '.join(arch.dependencies)}")

    return "\n".join(out)


# ─── 6. Hierarchical Context Management ──────────────────────────────────────
class HierarchicalContextManager:
    """Progressive disclosure context manager to prevent prompt saturation.
    
    Structure:
    - Tier 0: Project Memory & Architecture (Macro)
    - Tier 1: Subsystem Scope (Meso)
    - Tier 2: Symbol & Interface Skeleton (Micro)
    - Tier 3: Deep Context (Target code, call graph, tests)
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def get_context(
        self,
        task_query: str,
        subsystem: str = "",
        depth: str = "auto",
    ) -> str:
        """Retrieve hierarchical context targeted to the active task."""
        lines: list[str] = []

        # Tier 0: Macro Project Memory (Always concise)
        lines.append("## 🧭 Tier 0: Project Memory & Invariants")
        lines.append(f"- **Project**: `{self.workspace.name}` (Autonomous Sovereign AI Operating Layer & SWE Engine)")
        lines.append("- **Core Tenets**: Local privacy, zero user friction, multi-agent departmental autonomy, atomic safety.")
        lines.append("- **Active Runtime**: Python 3.11+, FastAPI, SQLite persistence, Playwright browser, Peacant worker.")

        if depth in ("0", "macro", "project"):
            return "\n".join(lines)

        # Tier 1: Subsystem Context
        detected_subsystem = subsystem.strip()
        if not detected_subsystem:
            low_q = task_query.lower()
            if any(k in low_q for k in ("swe", "patch", "code", "syntax", "refactor", "ast", "test")):
                detected_subsystem = "swe_engine"
            elif any(k in low_q for k in ("media", "audio", "video", "slideshow", "audiogram", "tts")):
                detected_subsystem = "media_studio"
            elif any(k in low_q for k in ("memory", "blackboard", "recall", "graph")):
                detected_subsystem = "memory"
            elif any(k in low_q for k in ("agent", "delegate", "department", "roster")):
                detected_subsystem = "agents"
            else:
                detected_subsystem = "core"

        lines.append(f"\n## 🏛️ Tier 1: Active Subsystem Context (`{detected_subsystem}`)")
        if detected_subsystem == "swe_engine":
            lines.append("- **Subsystem**: Dedicated SWE Coding Engine (`zenith/tools/swe_engine.py`, `zenith/tools/repo_intelligence.py`)")
            lines.append("- **Capabilities**: `repo_map`, `call_graph`, `analyze_dependency_graph`, `map_tests`, `apply_patch_transaction`, `rollback_patch`.")
        elif detected_subsystem == "media_studio":
            lines.append("- **Subsystem**: Creative & Media Studio (`zenith/tools/media_studio.py`)")
            lines.append("- **Capabilities**: `create_audiogram`, `create_slideshow`, `normalize_audio`, `overlay_media`, `burn_subtitles`, Edge TTS.")
        elif detected_subsystem == "memory":
            lines.append("- **Subsystem**: Long-Term Persistence (`zenith/memory/store.py`)")
            lines.append("- **Capabilities**: SQLite cognitive store, `org_blackboard`, timeline events, secret redaction.")
        else:
            lines.append(f"- **Subsystem**: General Orchestration (`zenith/core/`)")

        if depth in ("1", "subsystem"):
            return "\n".join(lines)

        # Tier 2: Symbol & Interface Skeleton (Semantic matching)
        lines.append("\n## 🧩 Tier 2: Relevant Interface Skeletons")
        search_engine = SemanticCodeSearchEngine(self.workspace)
        search_engine.index()
        top_chunks = search_engine.search(task_query, top_k=5)
        for chunk, score in top_chunks:
            lines.append(f"- `{chunk.file_path}:{chunk.line_number}` `{chunk.kind}:{chunk.symbol_name}` — {chunk.docstring[:80] if chunk.docstring else 'interface definition'}")

        if depth in ("2", "symbols"):
            return "\n".join(lines)

        # Tier 3: Deep Task Context (Test Mapping & Execution Paths)
        lines.append("\n## 🔬 Tier 3: Deep Verification & Call Paths")
        if top_chunks:
            primary_symbol = top_chunks[0][0].symbol_name
            test_map_res = TestMapper(self.workspace).map_target(primary_symbol)
            if test_map_res.matching_test_files:
                lines.append(f"- **Mapped Tests for `{primary_symbol}`**: `{', '.join(test_map_res.matching_test_files)}`")
                lines.append(f"- **Verification**: `{test_map_res.suggested_command}`")

        return "\n".join(lines)


async def get_hierarchical_context(
    task_query: str,
    subsystem: str = "",
    depth: str = "auto",
    repo_path: str = "",
) -> str:
    """Retrieve hierarchical context (Project Memory -> Subsystem -> Interface Skeletons -> Deep Context).
    
    Prevents context saturation on large repos.
    
    Args:
        task_query: Active engineering task description or user query.
        subsystem: Specific subsystem (optional, e.g. 'swe_engine', 'media_studio', 'memory').
        depth: 'auto', '0' (project), '1' (subsystem), '2' (symbols), '3' (deep).
        repo_path: Workspace directory.
    """
    workspace = _resolve_workspace(repo_path)
    mgr = HierarchicalContextManager(workspace)
    return await mgr.get_context(task_query=task_query, subsystem=subsystem, depth=depth)
