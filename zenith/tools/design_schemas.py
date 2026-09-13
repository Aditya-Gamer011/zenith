"""Zenith — Design Tool Schemas & Registry.

Describes available design operations per provider, their parameters,
required permissions, and known limitations. Used by the AI to understand
what design actions are available.
"""
from __future__ import annotations

# ── Design Tool Registry ─────────────────────────────────────────────────────

DESIGN_TOOL_REGISTRY = {
    "figma": {
        "name": "Figma",
        "description": "Professional UI/UX design tool for interface design, prototyping, and design systems.",
        "capabilities": {
            "read": {
                "user_info": {
                    "description": "Get the connected Figma user's profile (name, email, avatar)",
                    "scope": "current_user:read",
                    "tool": "figma_get_user",
                },
                "file_metadata": {
                    "description": "Read a Figma file's name, pages, version history",
                    "scope": "file_content:read",
                    "tool": "figma_read_file",
                },
                "node_properties": {
                    "description": "Inspect specific design nodes (frames, text, shapes) and their properties",
                    "scope": "file_content:read",
                    "tool": "figma_inspect_nodes",
                },
                "comments": {
                    "description": "Read comments on a Figma file",
                    "scope": "file_content:read",
                    "tool": "figma_read_comments",
                },
            },
            "export": {
                "images": {
                    "description": "Export design nodes as PNG, SVG, JPG, or PDF",
                    "scope": "file_content:read",
                    "tool": "figma_export_assets",
                    "formats": ["png", "svg", "jpg", "pdf"],
                },
            },
            "create": {
                "plugin_commands": {
                    "description": "Create and modify design elements via the Figma Plugin Bridge (requires plugin installed in Figma)",
                    "scope": "plugin",
                    "tool": "figma_plugin_command",
                    "note": "Direct file manipulation requires the Figma Plugin API, not the REST API. The REST API is read-only for design content.",
                },
            },
        },
        "limitations": [
            "The Figma REST API cannot create or modify file content directly.",
            "Creating frames, text, shapes requires the Figma Plugin Bridge.",
            "File writes require the Figma Plugin to be running in the user's Figma session.",
            "Rate limits: 30 requests per minute for most endpoints.",
        ],
    },
    "canva": {
        "name": "Canva",
        "description": "Online graphic design platform for creating presentations, social media graphics, and marketing materials.",
        "capabilities": {
            "read": {
                "user_info": {
                    "description": "Get the connected Canva user's profile",
                    "scope": "profile:read",
                    "tool": "canva_get_profile",
                },
                "designs": {
                    "description": "List and search the user's Canva designs",
                    "scope": "design:meta:read",
                    "tool": "canva_list_designs",
                },
            },
            "create": {
                "design": {
                    "description": "Create a new Canva design with specified dimensions",
                    "scope": "design:content:read",
                    "tool": "canva_create_design",
                },
            },
            "export": {
                "design": {
                    "description": "Export a Canva design as PNG, JPG, or PDF",
                    "scope": "design:content:read",
                    "tool": "canva_export_design",
                    "formats": ["png", "jpg", "pdf"],
                },
            },
        },
        "limitations": [
            "Canva Connect API does not support directly modifying design elements (text, shapes, colors).",
            "Design creation creates empty designs — content must be added through Canva's editor.",
            "Some design types require specific Canva plan subscriptions.",
            "Asset upload requires additional scopes (asset:write) not requested by default.",
        ],
    },
}


# ── Design Concepts ──────────────────────────────────────────────────────────
# Mapping of design concepts the AI should understand

DESIGN_CONCEPTS = {
    "frames": "Container elements that define regions. In Figma, these are the primary layout container. In Canva, these are design pages.",
    "typography": "Text styling including font family, size, weight, line height, letter spacing, and paragraph spacing.",
    "colors": "Fill colors, gradients, opacity. Represented as RGBA or hex values. Design systems use color tokens.",
    "layout": "Spatial arrangement using auto-layout (Figma), grids, constraints, and alignment.",
    "spacing": "Padding, margins, and gaps between elements. Consistent spacing creates visual rhythm.",
    "components": "Reusable design elements with variants. In Figma, these are components and instances.",
    "hierarchy": "Visual importance ordering through size, color, weight, and position.",
    "responsive": "Designs that adapt to different screen sizes using constraints and breakpoints.",
    "design_systems": "Organized collections of reusable components, styles, and guidelines.",
    "contrast": "Difference between elements. WCAG guidelines require minimum contrast ratios for accessibility.",
}


# ── Figma Plugin Command Types ───────────────────────────────────────────────
# Validated command types for the Figma Plugin Bridge

PLUGIN_COMMAND_TYPES = {
    "create_frame": {
        "description": "Create a new frame (artboard)",
        "params": {
            "name": {"type": "string", "required": True},
            "width": {"type": "number", "required": True},
            "height": {"type": "number", "required": True},
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
            "fill_color": {"type": "string", "description": "Hex color e.g. #1a1a2e"},
        },
    },
    "create_text": {
        "description": "Create a text layer",
        "params": {
            "text": {"type": "string", "required": True},
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
            "width": {"type": "number"},
            "font_size": {"type": "number", "default": 16},
            "font_family": {"type": "string", "default": "Inter"},
            "font_weight": {"type": "string", "default": "Regular"},
            "fill_color": {"type": "string", "default": "#ffffff"},
            "parent_id": {"type": "string", "description": "ID of parent frame"},
        },
    },
    "create_rectangle": {
        "description": "Create a rectangle shape",
        "params": {
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
            "width": {"type": "number", "required": True},
            "height": {"type": "number", "required": True},
            "fill_color": {"type": "string", "default": "#6366f1"},
            "corner_radius": {"type": "number", "default": 0},
            "parent_id": {"type": "string"},
            "name": {"type": "string"},
        },
    },
    "modify_node": {
        "description": "Modify properties of an existing node",
        "params": {
            "node_id": {"type": "string", "required": True},
            "name": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "width": {"type": "number"},
            "height": {"type": "number"},
            "fill_color": {"type": "string"},
            "opacity": {"type": "number"},
            "visible": {"type": "boolean"},
        },
    },
    "rename_node": {
        "description": "Rename a layer/node",
        "params": {
            "node_id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
        },
    },
}
