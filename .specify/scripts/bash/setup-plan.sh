#!/usr/bin/env bash

set -e

# Parse command line arguments
JSON_MODE=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=true ;;
        --help|-h) 
            echo "Usage: $0 [--json]"
            exit 0 
            ;;
        *) ARGS+=("$arg") ;;
    esac
done

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Get all paths and variables from common functions
eval $(get_feature_paths)

# [OPTIMIZED] Warn only, do not exit.
# This supports creating plans while remaining on the main branch.
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || true

# Ensure the feature directory exists
mkdir -p "$FEATURE_DIR"

# Copy plan template if it exists
TEMPLATE="$REPO_ROOT/.specify/templates/plan-template.md"
if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$IMPL_PLAN"
    if ! $JSON_MODE; then echo "Copied plan template to $IMPL_PLAN"; fi
else
    if ! $JSON_MODE; then echo "Warning: Plan template not found at $TEMPLATE"; fi
    touch "$IMPL_PLAN"
fi

# Output results
if $JSON_MODE; then
    printf '{"FEATURE_SPEC":"%s","IMPL_PLAN":"%s","SPECS_DIR":"%s","BRANCH":"%s","FEATURE_NAME":"%s"}\n' \
        "$FEATURE_SPEC" "$IMPL_PLAN" "$FEATURE_DIR" "$CURRENT_BRANCH" "$FEATURE_NAME"
else
    echo "FEATURE_SPEC: $FEATURE_SPEC"
    echo "IMPL_PLAN: $IMPL_PLAN" 
    echo "SPECS_DIR: $FEATURE_DIR"
    echo "FEATURE_NAME: $FEATURE_NAME" # Using logical name
    echo "GIT_BRANCH: $CURRENT_BRANCH" # Showing physical branch
fi