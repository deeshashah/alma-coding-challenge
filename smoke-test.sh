#!/usr/bin/env bash
# Basic smoke test against a running dev environment (see ./dev.sh).
#
# Flow: health check -> submit a test lead -> log in as an attorney ->
# confirm the lead shows up via the backend's GET /api/leads (the exact
# contract the dashboard reads from) -> confirm it also renders in the
# actual Next.js dashboard page (a real GET with the session cookie set
# manually, since that's the same thing the browser would send -- no
# fragile scraping of Next.js's internal Server Action wire format needed
# for a plain page GET).
#
# Env overrides (all optional, must match what the backend was started
# with -- ./dev.sh's defaults match these):
#   API_URL, FRONTEND_URL             default http://127.0.0.1:8000 / http://localhost:3000
#   ATTORNEY_EMAIL, ATTORNEY_PASSWORD default attorney@example.com / devpassword123

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

API_URL="${API_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
ATTORNEY_EMAIL="${ATTORNEY_EMAIL:-attorney@example.com}"
ATTORNEY_PASSWORD="${ATTORNEY_PASSWORD:-devpassword123}"
RESUME_FIXTURE="backend/tests/fixtures/dummy_resume.pdf"

PASS="\033[32m✓\033[0m"
FAIL="\033[31m✗\033[0m"

fail() {
  echo -e "$FAIL $1" >&2
  exit 1
}

echo "Running smoke test against:"
echo "  API:      $API_URL"
echo "  Frontend: $FRONTEND_URL"
echo ""

# 1. Health check
health_status=$(curl -fsS "$API_URL/api/health" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
[ "$health_status" = "ok" ] || fail "Backend health check failed (is ./dev.sh running?)"
echo -e "$PASS Backend healthy"

frontend_status=$(curl -fsS -o /dev/null -w "%{http_code}" "$FRONTEND_URL/" 2>/dev/null || echo "000")
[ "$frontend_status" = "200" ] || fail "Frontend not reachable at $FRONTEND_URL (got HTTP $frontend_status)"
echo -e "$PASS Frontend reachable"

# 2. Submit a test lead
[ -f "$RESUME_FIXTURE" ] || fail "Missing resume fixture at $RESUME_FIXTURE"
test_email="smoke-test+$(date +%s)@example.com"
lead_response=$(curl -fsS -X POST "$API_URL/api/leads" \
  -F "firstName=Smoke" \
  -F "lastName=Test" \
  -F "email=$test_email" \
  -F "resume=@$RESUME_FIXTURE;type=application/pdf") || fail "POST /api/leads failed"

lead_id=$(echo "$lead_response" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
[ -n "$lead_id" ] || fail "Lead submission didn't return an id: $lead_response"
echo -e "$PASS Submitted test lead ($test_email, id=$lead_id)"

# 3. Log in
login_response=$(curl -fsS -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ATTORNEY_EMAIL\",\"password\":\"$ATTORNEY_PASSWORD\"}") \
  || fail "POST /api/auth/login failed -- is the seeded attorney account set up? (./dev.sh seeds $ATTORNEY_EMAIL by default)"

token=$(echo "$login_response" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
[ -n "$token" ] || fail "Login didn't return a token: $login_response"
echo -e "$PASS Logged in as $ATTORNEY_EMAIL"

# 4. Confirm the lead appears via the backend contract the dashboard reads
leads_response=$(curl -fsS "$API_URL/api/leads?pageSize=100" -H "Authorization: Bearer $token") \
  || fail "GET /api/leads failed"

found=$(echo "$leads_response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('yes' if any(item['id'] == '$lead_id' for item in data['items']) else 'no')
" 2>/dev/null || echo "no")
[ "$found" = "yes" ] || fail "Test lead not found in GET /api/leads response"
echo -e "$PASS Lead appears in GET /api/leads"

# 5. Confirm it renders in the actual dashboard page
dashboard_html=$(curl -fsS --cookie "session_token=$token" "$FRONTEND_URL/dashboard") \
  || fail "GET /dashboard failed"

echo "$dashboard_html" | grep -q "$test_email" \
  || fail "Test lead's email not found in the rendered /dashboard HTML"
echo -e "$PASS Lead renders in the dashboard page"

echo ""
echo -e "\033[32mAll smoke tests passed.\033[0m"
