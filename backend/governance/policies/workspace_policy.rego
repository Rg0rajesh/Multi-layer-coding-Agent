package agentx.authz

# Default-deny: if input doesn't match any rule below, nothing is granted.
default allowed_scope = {"tools": [], "files": []}

allowed_scope = scope if {
    not requires_git
    scope := {"tools": base_tools, "files": safe_files}
}

allowed_scope = scope if {
    requires_git
    scope := {"tools": array.concat(base_tools, ["git"]), "files": safe_files}
}

requires_git if {
    input.git_integration == true
}

# Code execution is separately scoped and still runs inside the isolated
# Piston service. It is not filesystem or network access.
allowed_tool_names = {"file_read", "file_write", "pytest", "code_execute"}

base_tools = [t |
    t := input.requested_tools[_]
    allowed_tool_names[t]
]

safe_files = [f |
    f := input.touched_files[_]
    not escapes_workspace(f)
]

escapes_workspace(path) if {
    startswith(path, "..")
}

escapes_workspace(path) if {
    startswith(path, "/")
}
