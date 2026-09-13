"""Memory tool — read & write Zenith's long-term memory and knowledge graph."""
from __future__ import annotations

from ..memory import store


async def memory(action: str, key: str = "", value: str = "", query: str = "") -> str:
    action = (action or "").lower()
    if action == "save":
        if not key or not value:
            return "Save requires both key (category::name) and value."
        category, _, name = key.partition("::")
        if not name:
            name = category
            category = "general"
        store.save_memory(category.strip() or "general", name.strip(), value.strip())
        # Also persist to Mem0 multi-tier memory layer for structured recall & secret sanitization
        try:
            from ..services.memory_layer import memory_layer
            tier = "preference" if category.lower() in ("pref", "preference", "user", "habit") else "project"
            memory_layer.add_memory(
                content=f"{name}: {value}",
                tier=tier,
                topic=name,
                meta={"source": "memory_tool", "legacy_category": category},
            )
        except Exception:
            pass
        return f"Saved to memory ({category.strip() or 'general'}::{name.strip()})."
    if action == "recall":
        q = query or key or "."
        rows = store.recall_memory(q)
        out = []
        if rows:
            out.extend([f"[{r['category']}] {r['key']}: {r['value']}" for r in rows])
        # Also recall from Mem0 multi-tier layer
        try:
            from ..services.memory_layer import memory_layer
            mem0_res = memory_layer.recall(q, limit=5)
            for m in mem0_res:
                content = m.get("content", "")
                topic = m.get("topic", "")
                tier = m.get("tier", "memory")
                entry = f"[{tier}] {topic}: {content}"
                if content and not any(content in o for o in out):
                    out.append(entry)
        except Exception:
            pass
        if not out:
            return f"No memory found for '{q}'."
        return "\n".join(out)
    if action == "all":
        rows = store.all_memories()
        out = []
        if rows:
            out.extend([f"[{r['category']}] {r['key']}: {r['value']}" for r in rows])
        try:
            from ..services.memory_layer import memory_layer
            mem0_res = memory_layer.recall("", limit=20)
            for m in mem0_res:
                content = m.get("content", "")
                topic = m.get("topic", "")
                tier = m.get("tier", "memory")
                entry = f"[{tier}] {topic}: {content}"
                if content and not any(content in o for o in out):
                    out.append(entry)
        except Exception:
            pass
        if not out:
            return "No memories yet."
        return "\n".join(out)
    return "Unknown memory action."


async def graph(query: str = "") -> str:
    if not query:
        stats = store.graph_stats()
        return f"Graph: {stats['entities']} entities, {stats['edges']} relations."
    rows = store.query_graph(query)
    if not rows:
        return f"No graph matches for '{query}'."
    return "\n".join(f"{r['source']} --[{r['rel']}]--> {r['target']}" for r in rows)