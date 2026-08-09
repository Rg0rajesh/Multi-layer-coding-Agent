package agentx.authz

# Default-deny: if input doesn't match any rule below, nothing is granted.
default allowed_scope = {"tools": [], "files": []}

allowed_scope = scope {
    not requires_git
    scope := {
        "tools": base_tools,
        "files": safe_files,
    }
}

allowed_scope = scope {
    requires_git
    scope := {
        "tools": array.concat(base_tools, ["git"]),
        "files": safe_files,
    }
}

# Stable API contract consumed by governance/opa_client.py.
# OPA evaluates data.agentx.authz.scope and the client reads
# result.allowed_scope.
scope = {"allowed_scope": allowed_scope}

requires_git {
    input.git_integration == true
}

allowed_tool_names = {"file_read", "file_write", "pytest"}

base_tools = [t |
    t := input.requested_tools[_]
    allowed_tool_names[t]
]

# Files outside the task's own workspace never get file_write, no matter
# what the Planner asked for.
safe_files = [f |
    f := input.touched_files[_]
    not escapes_workspace(f)
]

escapes_workspace(path) {
    startswith(path, "..")
}

escapes_workspace(path) {
    startswith(path, "/")
}
