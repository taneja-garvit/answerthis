#!/usr/bin/env bash
# Walks the seeded demo through the full review flow with curl (requires jq).
#
#   ./scripts/demo_flow.sh                 # against http://localhost:8000
#   BASE_URL=http://host:port ./scripts/demo_flow.sh
#   RESET=1 ./scripts/demo_flow.sh         # recreate the demo first (clears reviews)
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
OUT_DIR="${OUT_DIR:-$(mktemp -d)}"
JSON=(-H "Content-Type: application/json")

step() { printf '\n== %s\n' "$1"; }

step "1. Health"
curl -fsS "$BASE_URL/health" | jq .

step "2. Create or load the seeded demo"
reset_query=""
[[ "${RESET:-}" == "1" ]] && reset_query="?reset=true"
demo=$(curl -fsS -X POST "$BASE_URL/api/demo$reset_query")
echo "$demo" | jq .
project_id=$(echo "$demo" | jq -r .project_id)
draft_id=$(echo "$demo" | jq -r .draft_id)

step "3. Project"
curl -fsS "$BASE_URL/api/projects/$project_id" | jq '{title, is_demo, drafts}'

step "4. Claims"
claims=$(curl -fsS "$BASE_URL/api/drafts/$draft_id/claims")
echo "$claims" | jq '.claims[] | {order, claim_text, verdict: .assessment.verdict, review_status}'
claim1=$(echo "$claims" | jq -r '.claims[0].id')
claim2=$(echo "$claims" | jq -r '.claims[1].id')
claim3=$(echo "$claims" | jq -r '.claims[2].id')

step "5. One claim (mortality figure mismatch)"
curl -fsS "$BASE_URL/api/claims/$claim2" \
  | jq '{claim_text, evidence: [.evidence[].passage], assessment: .assessment | {verdict, confidence, issues}}'

step "6. KEEP claim 1"
curl -fsS -X PUT "$BASE_URL/api/claims/$claim1/review" "${JSON[@]}" \
  -d '{"decision":"KEEP","reviewer_note":"Figure, outcome and comparator match the abstract (OR 0.78, 95% CI 0.70–0.87)."}' \
  | jq '{review_status, review: .review.decision}'

step "7. QUALIFY claim 2 with revised wording"
curl -fsS -X PUT "$BASE_URL/api/claims/$claim2/review" "${JSON[@]}" \
  -d '{"decision":"QUALIFY","reviewer_note":"Changed 22% to 19% and retained odds terminology.","revised_claim":"Non-invasive remote patient monitoring was associated with approximately 19% lower odds of death compared with usual care (pooled OR 0.81, 95% CI 0.69–0.95)."}' \
  | jq '{review_status, review: .review | {decision, revised_claim}}'

step "8. REMOVE claim 3"
curl -fsS -X PUT "$BASE_URL/api/claims/$claim3/review" "${JSON[@]}" \
  -d '{"decision":"REMOVE","reviewer_note":"Pooled trial estimates do not support benefit for every patient."}' \
  | jq '{review_status, review: .review.decision}'

step "8b. REPLACE without revised_claim is rejected (expect 422)"
curl -sS -o /dev/stderr -w '%{http_code}\n' -X PUT "$BASE_URL/api/claims/$claim1/review" \
  "${JSON[@]}" -d '{"decision":"REPLACE"}' 2>/dev/null

step "9. Progress (expect 3 / 3)"
curl -fsS "$BASE_URL/api/projects/$project_id/progress" | jq .

step "10. Export JSON"
curl -fsS -o "$OUT_DIR/audit.json" "$BASE_URL/api/projects/$project_id/export?format=json"
jq '.claims[] | {order, verdict: .assessment.verdict, decision: .review.decision, history: [.review_history[].decision]}' "$OUT_DIR/audit.json"

step "11. Export CSV"
curl -fsS -o "$OUT_DIR/audit.csv" "$BASE_URL/api/projects/$project_id/export?format=csv"
head -c 600 "$OUT_DIR/audit.csv"; echo " ..."

step "12. Persistence check (fresh read)"
curl -fsS "$BASE_URL/api/projects/$project_id/audit" \
  | jq -e '[.claims[].review.decision] == ["KEEP","QUALIFY","REMOVE"]' >/dev/null \
  && echo "Decisions persisted: KEEP, QUALIFY, REMOVE"

echo
echo "Exports written to $OUT_DIR"
