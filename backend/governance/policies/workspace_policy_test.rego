package agentx.authz

import rego.v1

# Policy contract: the API client evaluates data.agentx.authz.scope
# and expects the granted scope under the `allowed_scope` key.
test_scope_denies_disallowed_tools_and_absolute_paths if {
    result := scope with input as {
        "requested_tools": ["file_read", "shell", "pytest"],
        "touched_files": ["src/main.py", "../outside.py", "/etc/passwd"],
        "language": "python",
    }
    result.allowed_scope.tools == ["file_read", "pytest"]
    result.allowed_scope.files == ["src/main.py"]
}

test_scope_adds_git_only_when_requested if {
    result := scope with input as {
        "requested_tools": ["file_read", "pytest"],
        "touched_files": ["src/main.py"],
        "git_integration": true,
    }
    result.allowed_scope.tools == ["file_read", "pytest", "git"]
}

test_scope_defaults_to_no_tools_when_input_is_missing if {
    result := scope with input as {}
    result.allowed_scope.tools == []
    result.allowed_scope.files == []
}
