#!/bin/bash
# Test Runner for Phase 2 Database Tests
# Usage: ./supabase/tests/run_tests.sh [local|remote]

set -e

DB_URL="${1:-local}"

if [ "$DB_URL" = "local" ]; then
    DB_HOST="localhost"
    DB_PORT="55432"
    DB_NAME="postgres"
    DB_USER="postgres"
    DB_PASS="postgres"
elif [ "$DB_URL" = "remote" ]; then
    echo "Remote execution disabled by default. Set SUPABASE_DB_* env vars and pass 'remote' explicitly if needed."
    exit 1
else
    echo "Usage: $0 [local|remote]"
    exit 1
fi

export PGPASSWORD="$DB_PASS"

echo "Running Phase 2 Database Tests against $DB_HOST:$DB_PORT/$DB_NAME"
echo "============================================================"

run_test() {
    local test_file=$1
    local test_name=$2
    local is_manual=$3
    echo ""
    echo ">>> $test_name"
    echo "------------------------------------------------------------"
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$test_file" -v ON_ERROR_STOP=1 2>&1; then
        echo "✓ $test_name PASSED"
        return 0
    else
        echo "✗ $test_name FAILED"
        return 1
    fi
}

# Track results
PASSED=0
FAILED=0
MANUAL=0

# Automated test suites (executable assertions)
echo "=== Automated Test Suites ==="
for test in \
    "supabase/tests/00_security_assertions.sql|Security Assertions|false" \
    "supabase/tests/01_schema_integrity.sql|Schema Integrity|false" \
    "supabase/tests/03_workflow_integrity.sql|Workflow Integrity|false"; do

    IFS='|' read -r file name manual <<< "$test"

    if run_test "$file" "$name" "$manual"; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
    fi
done

# Manual test suites (documented scenarios, not executable assertions)
echo ""
echo "=== Manual Test Suites (documented scenarios, not executed) ==="
for test in \
    "supabase/tests/02_org_isolation_rls.sql|Organization Isolation (manual)" \
    "supabase/tests/04_security_atomicity.sql|Security Atomicity (manual)"; do

    IFS='|' read -r file name manual <<< "$test"
    MANUAL=$((MANUAL + 1))
    echo ""
    echo ">>> $name"
    echo "------------------------------------------------------------"
    echo "  (Documented scenarios - requires manual execution under authenticated contexts)"
    echo "  File: $file"
    echo "  Status: SKIPPED (manual)"
done

echo ""
echo "============================================================"
echo "Test Summary:"
echo "  Automated suites passed: $PASSED"
echo "  Automated suites failed: $FAILED"
echo "  Manual suites documented: $MANUAL"
echo "============================================================"

# Count actual assertions from security test
if [ -f "supabase/tests/00_security_assertions.sql" ]; then
    ASSERTION_COUNT=$(grep -c "RAISE NOTICE 'PASS" supabase/tests/00_security_assertions.sql 2>/dev/null || echo 0)
    echo "  Security assertions in automated suite: $ASSERTION_COUNT"
fi

if [ $FAILED -gt 0 ]; then
    exit 1
fi