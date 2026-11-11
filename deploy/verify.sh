#!/usr/bin/env bash
set -euo pipefail

request() {
    local expected=$1
    shift
    local result status elapsed
    printf '$ curl'
    printf ' %q' "$@"
    printf '\n'
    result=$(curl --silent --show-error --max-time 12 --write-out '\n%{http_code} %{time_total}' "$@")
    body=${result%$'\n'*}
    read -r status elapsed <<< "${result##*$'\n'}"
    printf 'HTTP %s (%s s)\n%s\n' "$status" "$elapsed" "$body"
    [[ "$status" == "$expected" ]]
}

users=http://127.0.0.1:5001
orders=http://127.0.0.1:5002
gateway=http://127.0.0.1
json=(-H 'Content-Type: application/json')

echo '=== HEALTH AND SUCCESS ==='
request 200 "$users/health"
request 200 "$orders/health"
request 201 "${json[@]}" -d '{"email":"demo@example.com","name":"Демо"}' "$users/users"
user_id=$(jq -er .id <<< "$body")
payload=$(jq -nc --argjson id "$user_id" '{user_id:$id,total:1500.50}')
request 201 "${json[@]}" -d "$payload" "$orders/orders"
order_id=$(jq -er .id <<< "$body")
request 200 "$orders/orders/$order_id"
request 404 "${json[@]}" -d '{"user_id":99999999,"total":100}' "$orders/orders"

echo '=== DEPENDENCY OUTAGE ==='
echo '$ docker compose stop user-service'
docker compose stop user-service
for attempt in 1 2 3 4 5; do
    printf 'Failed logical request %s of 5\n' "$attempt"
    request 503 "${json[@]}" -d "$payload" "$orders/orders"
    [[ $(jq -er .code <<< "$body") == user_service_unavailable ]]
done
request 503 "${json[@]}" -d "$payload" "$orders/orders"
[[ $(jq -er .code <<< "$body") == circuit_open ]]
request 200 "$orders/health"
[[ $(jq -er .circuit_breaker <<< "$body") == open ]]
request 200 "$orders/orders/$order_id"

echo '=== RESTART AND VOLUMES ==='
docker compose start --wait user-service
echo '$ docker compose restart user-service order-service'
docker compose restart user-service order-service
docker compose up --wait --wait-timeout 60
request 200 "$users/users/$user_id"
[[ $(jq -er .id <<< "$body") == "$user_id" ]]
request 200 "$orders/orders/$order_id"
[[ $(jq -er .id <<< "$body") == "$order_id" ]]

echo '=== GATEWAY AND RATE LIMIT ==='
request 200 "$gateway/api/users/$user_id"
sleep 0.2
request 200 "$gateway/api/orders/$order_id"
sleep 0.2
statuses=$(seq 1 12 | xargs -P 12 -I {} curl --silent --max-time 5 --output /dev/null --write-out '%{http_code}\n' "$gateway/api/orders")
printf 'Parallel request status counts:\n'
sort <<< "$statuses" | uniq -c
grep -qx 200 <<< "$statuses"
grep -qx 429 <<< "$statuses"
