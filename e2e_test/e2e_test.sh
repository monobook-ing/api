#!/bin/bash

# ============================================================================
# Complete E2E Testing Script
# ============================================================================
# Usage:
#   ./e2e_test.sh [options]
#
# Options:
#   --clean-db          Clean database before running tests
#   --debug             Enable debug mode (verbose output)
#   --help              Show this help message
#
# Examples:
#   ./e2e_test.sh --clean-db --debug
#   ./e2e_test.sh --debug
# ============================================================================

set -e

# Configuration
BASE_URL="http://localhost:8000"
API_VERSION="v1.0"
API_URL="$BASE_URL/$API_VERSION"

# Customer data
CUSTOMER1_EMAIL="microsaas.farm@gmail.com"
NEW_TEAM_MEMBER_EMAIL="microsaas.farm+1@gmail.com"
NEW_TEAM_MEMBER_NAME="microsaas.farm+1"
CUSTOMER1_FIRST_NAME=""
CUSTOMER1_ACCESS_TOKEN=""
UPDATED_FIRST_NAME="John"
UPDATED_LAST_NAME="Down"
MAGIC_TOKEN=""
NEW_TEAM_MEMBER_MAGIC_TOKEN=""
NEW_TEAM_MEMBER_ACCESS_TOKEN=""
NOTIFICATION_ID=""
INVITE_ACCEPTED_NOTIFICATION_ID=""
TEAM_MEMBER_ID=""
ADMIN_TEAM_MEMBER_ID=""

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
CURRENT_TEST=0

# Flags
CLEAN_DB=false
DEBUG=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo ""
    echo "================================================================"
    echo "  $1"
    echo "================================================================"
}

print_step() {
    CURRENT_TEST=$((CURRENT_TEST + 1))
    echo ""
    echo -e "${BLUE}📝 TEST STEP #$CURRENT_TEST: $1${NC}"
}

print_success() {
    PASSED_TESTS=$((PASSED_TESTS + 1))
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    FAILED_TESTS=$((FAILED_TESTS + 1))
    echo -e "${RED}❌ $1${NC}"
}

print_debug() {
    if [ "$DEBUG" = true ]; then
        echo -e "${CYAN}🔍 DEBUG: $1${NC}"
    fi
}

print_test_success() {
    echo ""
    echo -e "${GREEN}✨ TEST SUCCESSFUL! ✨${NC}"
    echo ""
}

cleanup_temp_files() {
    rm -f tmp_*.json 2>/dev/null || true
}

check_response() {
    local response_code=$1
    local expected_code=$2
    local description=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [[ "$response_code" == "$expected_code" ]]; then
        print_success "$description (HTTP $response_code)"
        return 0
    else
        print_error "$description (Expected HTTP $expected_code, got $response_code)"
        if [ "$DEBUG" = true ] && [ -f "tmp_error_response.json" ]; then
            echo "Response body:"
            cat tmp_error_response.json
        fi
        exit 1
    fi
}

check_response_any() {
    local response_code=$1
    local description=$2
    shift 2
    local expected_codes=("$@")

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    for code in "${expected_codes[@]}"; do
        if [[ "$response_code" == "$code" ]]; then
            print_success "$description (HTTP $response_code)"
            return 0
        fi
    done

    print_error "$description (Expected HTTP ${expected_codes[*]}, got $response_code)"
    if [ "$DEBUG" = true ] && [ -f "tmp_error_response.json" ]; then
        echo "Response body:"
        cat tmp_error_response.json
    fi
    exit 1
}

validate_json_field() {
    local file=$1
    local field=$2
    local expected=$3
    local description=$4
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local actual=$(jq -r "$field" "$file" 2>/dev/null || echo "null")
    
    if [[ "$actual" == "$expected" ]]; then
        print_success "$description: '$actual'"
        return 0
    else
        print_error "$description (Expected: '$expected', Got: '$actual')"
        exit 1
    fi
}

validate_json_not_null() {
    local file=$1
    local field=$2
    local description=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local value=$(jq -r "$field" "$file" 2>/dev/null || echo "null")
    
    if [[ "$value" != "null" && -n "$value" ]]; then
        print_success "$description: '$value'"
        return 0
    else
        print_error "$description is null or empty"
        exit 1
    fi
}

validate_array_length() {
    local file=$1
    local expected_length=$2
    local description=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local actual_length=$(jq 'length' "$file" 2>/dev/null || echo "0")
    
    if [[ "$actual_length" == "$expected_length" ]]; then
        print_success "$description: $actual_length items"
        return 0
    else
        print_error "$description (Expected: $expected_length, Got: $actual_length)"
        exit 1
    fi
}

validate_boolean() {
    local file=$1
    local field=$2
    local expected=$3
    local description=$4
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local actual=$(jq -r "$field" "$file" 2>/dev/null || echo "null")
    
    if [[ "$actual" == "$expected" ]]; then
        print_success "$description: $actual"
        return 0
    else
        print_error "$description (Expected: $expected, Got: $actual)"
        exit 1
    fi
}

print_debug_request() {
    if [ "$DEBUG" = true ]; then
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}📤 REQUEST:${NC}"
        echo "$1"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    fi
}

print_debug_response() {
    if [ "$DEBUG" = true ]; then
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}📥 RESPONSE (HTTP $1):${NC}"
        if [ -f "$2" ]; then
            cat "$2" | jq '.' 2>/dev/null || cat "$2"
        fi
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    fi
}

# ============================================================================
# Database Cleanup
# ============================================================================

clean_database() {
    if [ "$CLEAN_DB" = true ]; then
        print_header "DATABASE CLEANUP"
        if [ -f "./db_cleanup.sh" ]; then
            echo "Running database cleanup script..."
            ./db_cleanup.sh
            print_success "Database cleaned successfully"
        else
            echo "⚠️  Warning: db_cleanup.sh not found, skipping cleanup"
        fi
    fi
}

# ============================================================================
# Test Functions
# ============================================================================

# Step 1: Test Server Ping
test_step_1_server_ping() {
    print_step "Test Server Ping"
    
    local request="curl -s -w '%{http_code}' -o tmp_ping.json '$BASE_URL/ping'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_ping.json "$BASE_URL/ping")
    print_debug_response "$response" "tmp_ping.json"
    
    check_response "$response" "200" "Server ping"
    validate_json_field "tmp_ping.json" ".status" "ok" "Status field"
    
    print_test_success
}

# Step 2: Sign In as New Customer
test_step_2_signin_new_customer() {
    print_step "Sign In as New Customer"
    
    local request="curl -s -w '%{http_code}' -o tmp_signin.json -X POST '$API_URL/signin' -H 'Content-Type: application/json' -d '{\"email\": \"$CUSTOMER1_EMAIL\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_signin.json -X POST "$API_URL/signin" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$CUSTOMER1_EMAIL\"}")
    print_debug_response "$response" "tmp_signin.json"
    
    check_response "$response" "201" "Sign in request"
    validate_json_not_null "tmp_signin.json" ".token" "Magic token"
    validate_json_not_null "tmp_signin.json" ".expires_at" "Token expiration"
    
    MAGIC_TOKEN=$(jq -r '.token' tmp_signin.json)
    print_debug "Saved magic token: $MAGIC_TOKEN"
    
    print_test_success
}

# Step 3: Confirm Sign In with Different Email
test_step_3_confirm_wrong_email() {
    print_step "Confirm Sign In with Different Email (Should Fail)"
    
    local wrong_email="microsaas.farm+1@gmail.com"
    local request="curl -s -w '%{http_code}' -o tmp_confirm_wrong_email.json -X POST '$API_URL/signin/confirm' -H 'Content-Type: application/json' -d '{\"email\": \"$wrong_email\", \"token\": \"$MAGIC_TOKEN\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_confirm_wrong_email.json -X POST "$API_URL/signin/confirm" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$wrong_email\", \"token\": \"$MAGIC_TOKEN\"}")
    print_debug_response "$response" "tmp_confirm_wrong_email.json"
    
    check_response "$response" "400" "Confirm with wrong email"
    validate_json_field "tmp_confirm_wrong_email.json" ".detail" "Token does not match the provided email" "Error detail"
    
    print_test_success
}

# Step 4: Confirm Sign In with Wrong Token
test_step_4_confirm_wrong_token() {
    print_step "Confirm Sign In with Wrong Token (Should Fail)"
    
    local wrong_token="a1ec76f2-afe0-4c24-82cd-fe5bd03253b"
    local request="curl -s -w '%{http_code}' -o tmp_confirm_wrong_token.json -X POST '$API_URL/signin/confirm' -H 'Content-Type: application/json' -d '{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$wrong_token\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_confirm_wrong_token.json -X POST "$API_URL/signin/confirm" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$wrong_token\"}")
    print_debug_response "$response" "tmp_confirm_wrong_token.json"
    
    check_response "$response" "404" "Confirm with wrong token"
    validate_json_field "tmp_confirm_wrong_token.json" ".detail" "Invalid or expired magic link" "Error detail"
    
    print_test_success
}

# Step 5: Confirm Sign In Successfully
test_step_5_confirm_signin() {
    print_step "Confirm Sign In Successfully"
    
    local request="curl -s -w '%{http_code}' -o tmp_confirm.json -X POST '$API_URL/signin/confirm' -H 'Content-Type: application/json' -d '{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$MAGIC_TOKEN\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_confirm.json -X POST "$API_URL/signin/confirm" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$MAGIC_TOKEN\"}")
    print_debug_response "$response" "tmp_confirm.json"
    
    check_response "$response" "200" "Confirm sign in"
    validate_json_not_null "tmp_confirm.json" ".access_token" "Access token"
    validate_json_not_null "tmp_confirm.json" ".token_type" "Token type"
    validate_json_not_null "tmp_confirm.json" ".user.id" "User ID"
    validate_json_not_null "tmp_confirm.json" ".user.email" "User email"
    validate_json_not_null "tmp_confirm.json" ".user.name" "User name"
    validate_json_field "tmp_confirm.json" ".user.email" "$CUSTOMER1_EMAIL" "User email matches"
    
    CUSTOMER1_ACCESS_TOKEN=$(jq -r '.access_token' tmp_confirm.json)
    CUSTOMER1_FIRST_NAME=$(jq -r '.user.name' tmp_confirm.json)
    print_debug "Saved access token"
    print_debug "Saved first name: $CUSTOMER1_FIRST_NAME"
    
    print_test_success
}

# Step 6: Try to Confirm Again (Should Fail)
test_step_6_confirm_again() {
    print_step "Try to Confirm Again with Same Token (Should Fail)"
    
    local request="curl -s -w '%{http_code}' -o tmp_confirm_again.json -X POST '$API_URL/signin/confirm' -H 'Content-Type: application/json' -d '{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$MAGIC_TOKEN\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_confirm_again.json -X POST "$API_URL/signin/confirm" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$CUSTOMER1_EMAIL\", \"token\": \"$MAGIC_TOKEN\"}")
    print_debug_response "$response" "tmp_confirm_again.json"
    
    check_response "$response" "404" "Confirm again with same token"
    validate_json_field "tmp_confirm_again.json" ".detail" "Invalid or expired magic link" "Error detail"
    
    print_test_success
}

# Step 7: Get Current User
test_step_7_get_current_user() {
    print_step "Get Current User"
    
    local request="curl -s -w '%{http_code}' -o tmp_me.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/users/me'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_me.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/users/me")
    print_debug_response "$response" "tmp_me.json"
    
    check_response "$response" "200" "Get current user"
    validate_json_field "tmp_me.json" ".email" "$CUSTOMER1_EMAIL" "Email matches"
    validate_json_field "tmp_me.json" ".first_name" "$CUSTOMER1_FIRST_NAME" "First name matches"
    validate_json_not_null "tmp_me.json" ".default_account_id" "Default account ID"
    
    print_test_success
}

# Step 8: Update Current User
test_step_8_update_current_user() {
    print_step "Update Current User"

    local request="curl -s -w '%{http_code}' -o tmp_update_current_user.json -X PATCH -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' -H 'Content-Type: application/json' '$API_URL/users/me' -d '{\"first_name\":\"$UPDATED_FIRST_NAME\",\"last_name\":\"$UPDATED_LAST_NAME\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_update_current_user.json \
        -X PATCH \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL/users/me" \
        -d "{\"first_name\":\"$UPDATED_FIRST_NAME\",\"last_name\":\"$UPDATED_LAST_NAME\"}")
    print_debug_response "$response" "tmp_update_current_user.json"

    check_response "$response" "200" "Update current user"
    validate_json_field "tmp_update_current_user.json" ".first_name" "$UPDATED_FIRST_NAME" "Updated first name"
    validate_json_field "tmp_update_current_user.json" ".last_name" "$UPDATED_LAST_NAME" "Updated last name"

    UPDATED_FIRST_NAME=$(jq -r '.first_name' tmp_update_current_user.json)
    UPDATED_LAST_NAME=$(jq -r '.last_name' tmp_update_current_user.json)
    CUSTOMER1_FIRST_NAME="$UPDATED_FIRST_NAME"
    print_debug "Saved updated first name: $UPDATED_FIRST_NAME"
    print_debug "Saved updated last name: $UPDATED_LAST_NAME"

    print_test_success
}

# Step 9: Get Current User After Update
test_step_9_get_current_user_after_update() {
    print_step "Get Current User After Update"

    local request="curl -s -w '%{http_code}' -o tmp_me_after_update.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/users/me'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_me_after_update.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/users/me")
    print_debug_response "$response" "tmp_me_after_update.json"

    check_response "$response" "200" "Get current user after update"
    validate_json_field "tmp_me_after_update.json" ".email" "$CUSTOMER1_EMAIL" "Email remains correct after update"
    validate_json_field "tmp_me_after_update.json" ".first_name" "$UPDATED_FIRST_NAME" "First name updated correctly"
    validate_json_field "tmp_me_after_update.json" ".last_name" "$UPDATED_LAST_NAME" "Last name updated correctly"
    validate_json_not_null "tmp_me_after_update.json" ".default_account_id" "Default account ID still present"

    print_test_success
}

# Step 10: Get All User Notifications
test_step_10_get_notifications() {
    print_step "Get All User Notifications"
    
    local request="curl -s -w '%{http_code}' -o tmp_notifications.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notifications.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications")
    print_debug_response "$response" "tmp_notifications.json"
    
    check_response "$response" "200" "Get notifications"
    validate_json_field "tmp_notifications.json" ".items | length" "1" "Notifications count"
    validate_json_field "tmp_notifications.json" ".items[0].subject" "Welcome to fastapi-starter-kit!" "Notification subject"
    validate_json_field "tmp_notifications.json" ".items[0].body" "Thanks for joining fastapi-starter-kit! We're glad you're here." "Notification body"
    validate_json_field "tmp_notifications.json" ".items[0].type" "welcome" "Notification type"
    validate_boolean "tmp_notifications.json" ".items[0].is_read" "false" "Is read status"
    validate_json_field "tmp_notifications.json" ".next_cursor" "null" "Next cursor is null"
    
    NOTIFICATION_ID=$(jq -r '.items[0].id' tmp_notifications.json)
    print_debug "Saved notification ID: $NOTIFICATION_ID"
    
    print_test_success
}

# Step 11: Get Unread Notifications with Filter
test_step_11_get_unread_notifications_with_filter() {
    print_step "Get Unread Notifications with Filter"
    
    local request="curl -s -w '%{http_code}' -o tmp_notifications_filter_unread.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications?is_read=0'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notifications_filter_unread.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications?is_read=0")
    print_debug_response "$response" "tmp_notifications_filter_unread.json"
    
    check_response "$response" "200" "Get unread notifications with filter"
    validate_json_field "tmp_notifications_filter_unread.json" "if type==\"array\" then length else (.items // []) | length end" "1" "Unread notifications count"
    validate_boolean "tmp_notifications_filter_unread.json" "if type==\"array\" then .[0].is_read else .items[0].is_read end" "false" "Unread notification is marked unread"
    
    print_test_success
}

# Step 12: Get Read Notifications with Filter
test_step_12_get_read_notifications_with_filter() {
    print_step "Get Read Notifications with Filter"
    
    local request="curl -s -w '%{http_code}' -o tmp_notifications_filter_read.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications?is_read=1'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notifications_filter_read.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications?is_read=1")
    print_debug_response "$response" "tmp_notifications_filter_read.json"
    
    check_response "$response" "200" "Get read notifications with filter"
    validate_json_field "tmp_notifications_filter_read.json" "if type==\"array\" then length else (.items // []) | length end" "0" "Read notifications count"
    
    print_test_success
}

# Step 13: Get Notification Count
test_step_13_get_notification_count() {
    print_step "Get Notification Count"
    
    local request="curl -s -w '%{http_code}' -o tmp_notification_count.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notification_count.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count")
    print_debug_response "$response" "tmp_notification_count.json"
    
    check_response "$response" "200" "Get notification count"
    validate_json_field "tmp_notification_count.json" ".count" "1" "Notification count"
    
    print_test_success
}

# Step 14: Get Unread Notification Count
test_step_14_get_unread_notification_count() {
    print_step "Get Unread Notification Count"
    
    local request="curl -s -w '%{http_code}' -o tmp_notification_count_unread.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count?is_read=0'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notification_count_unread.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count?is_read=0")
    print_debug_response "$response" "tmp_notification_count_unread.json"
    
    check_response "$response" "200" "Get unread notification count"
    validate_json_field "tmp_notification_count_unread.json" ".count" "1" "Unread notification count"
    
    print_test_success
}

# Step 15: Get Read Notification Count
test_step_15_get_read_notification_count() {
    print_step "Get Read Notification Count"
    
    local request="curl -s -w '%{http_code}' -o tmp_notification_count_read.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count?is_read=1'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notification_count_read.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count?is_read=1")
    print_debug_response "$response" "tmp_notification_count_read.json"
    
    check_response "$response" "200" "Get read notification count"
    validate_json_field "tmp_notification_count_read.json" ".count" "0" "Read notification count"
    
    print_test_success
}

# Step 16: Mark All Notifications as Read
test_step_16_read_notifications() {
    print_step "Mark All Notifications as Read"
    
    local request="curl -s -w '%{http_code}' -o tmp_read_notifications.json -X POST -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/read'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_read_notifications.json \
        -X POST \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/read")
    print_debug_response "$response" "tmp_read_notifications.json"
    
    check_response "$response" "200" "Mark notifications as read"
    validate_array_length "tmp_read_notifications.json" "1" "Notifications count"
    validate_boolean "tmp_read_notifications.json" ".[0].is_read" "true" "Is read status"
    
    print_test_success
}

# Step 17: Get All Notifications Again
test_step_17_get_notifications_again() {
    print_step "Get All Notifications Again (Should Be Read)"
    
    local request="curl -s -w '%{http_code}' -o tmp_notifications_again.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notifications_again.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications")
    print_debug_response "$response" "tmp_notifications_again.json"
    
    check_response "$response" "200" "Get notifications again"
    validate_json_field "tmp_notifications_again.json" ".items | length" "1" "Notifications count"
    validate_json_field "tmp_notifications_again.json" ".items[0].subject" "Welcome to fastapi-starter-kit!" "Notification subject"
    validate_json_field "tmp_notifications_again.json" ".items[0].body" "Thanks for joining fastapi-starter-kit! We're glad you're here." "Notification body"
    validate_json_field "tmp_notifications_again.json" ".items[0].type" "welcome" "Notification type"
    validate_boolean "tmp_notifications_again.json" ".items[0].is_read" "true" "Is read status"
    validate_json_field "tmp_notifications_again.json" ".next_cursor" "null" "Next cursor is null"
    
    print_test_success
}

# Step 18: Get Notification by ID
test_step_18_get_notification_by_id() {
    print_step "Get Notification by ID"
    
    local request="curl -s -w '%{http_code}' -o tmp_notification_by_id.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/$NOTIFICATION_ID'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_notification_by_id.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/$NOTIFICATION_ID")
    print_debug_response "$response" "tmp_notification_by_id.json"
    
    check_response "$response" "200" "Get notification by ID"
    validate_json_field "tmp_notification_by_id.json" ".subject" "Welcome to fastapi-starter-kit!" "Notification subject"
    validate_json_field "tmp_notification_by_id.json" ".body" "Thanks for joining fastapi-starter-kit! We're glad you're here." "Notification body"
    validate_json_field "tmp_notification_by_id.json" ".type" "welcome" "Notification type"
    validate_boolean "tmp_notification_by_id.json" ".is_read" "true" "Is read status"
    
    print_test_success
}

# Step 19: Get All Team Members
test_step_19_get_team_members() {
    print_step "Get All Team Members"
    
    local request="curl -s -w '%{http_code}' -o tmp_team_members.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_team_members.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members")
    print_debug_response "$response" "tmp_team_members.json"
    
    check_response "$response" "200" "Get team members"
    validate_json_field "tmp_team_members.json" ".items | length" "1" "Team members count"
    validate_json_field "tmp_team_members.json" ".items[0].role" "owner" "Member role"
    validate_json_field "tmp_team_members.json" ".items[0].status" "accepted" "Member status"
    validate_json_field "tmp_team_members.json" ".next_cursor" "null" "Next cursor is null"

    # Check name contains first_name
    local team_member_name=$(jq -r '.items[0].name' tmp_team_members.json)
    if [[ "$team_member_name" == *"$CUSTOMER1_FIRST_NAME"* ]]; then
        print_success "Team member name contains first name: '$team_member_name'"
    else
        print_error "Team member name does not contain first name (Expected: *$CUSTOMER1_FIRST_NAME*, Got: $team_member_name)"
        exit 1
    fi

    TEAM_MEMBER_ID=$(jq -r '.items[0].id' tmp_team_members.json)
    print_debug "Saved team member ID: $TEAM_MEMBER_ID"
    
    print_test_success
}

# Step 20: Get Team Member by ID
test_step_20_get_team_member_by_id() {
    print_step "Get Team Member by ID"
    
    local request="curl -s -w '%{http_code}' -o tmp_team_member_by_id.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members/$TEAM_MEMBER_ID'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_team_member_by_id.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members/$TEAM_MEMBER_ID")
    print_debug_response "$response" "tmp_team_member_by_id.json"
    
    check_response "$response" "200" "Get team member by ID"
    validate_json_field "tmp_team_member_by_id.json" ".id" "$TEAM_MEMBER_ID" "Member ID"
    validate_json_field "tmp_team_member_by_id.json" ".role" "owner" "Member role"
    validate_json_field "tmp_team_member_by_id.json" ".status" "accepted" "Member status"
    validate_json_field "tmp_team_member_by_id.json" ".name" "$CUSTOMER1_FIRST_NAME" "Member name"
    
    print_test_success
}

# Step 21: Try to Update Team Member (Should Fail)
test_step_21_update_team_member() {
    print_step "Try to Update Team Member (Should Fail)"
    
    local request="curl -s -w '%{http_code}' -o tmp_update_team_member.json -X PATCH -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' -H 'Content-Type: application/json' '$API_URL/team_members/$TEAM_MEMBER_ID' -d '{\"role\":\"admin\"}'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_update_team_member.json \
        -X PATCH \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL/team_members/$TEAM_MEMBER_ID" \
        -d '{"role":"admin"}')
    print_debug_response "$response" "tmp_update_team_member.json"
    
    check_response "$response" "400" "Update team member owner role"
    validate_json_field "tmp_update_team_member.json" ".detail" "Cannot update the account owner" "Error detail"
    
    print_test_success
}

# Step 22: Try to Delete Team Member (Should Fail)
test_step_22_delete_team_member() {
    print_step "Try to Delete Team Member (Should Fail)"
    
    local request="curl -s -w '%{http_code}' -o tmp_delete_team_member.json -X DELETE -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members/$TEAM_MEMBER_ID'"
    print_debug_request "$request"
    
    local response=$(curl -s -w "%{http_code}" -o tmp_delete_team_member.json \
        -X DELETE \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members/$TEAM_MEMBER_ID")
    print_debug_response "$response" "tmp_delete_team_member.json"
    
    check_response "$response" "400" "Delete team member owner"
    validate_json_field "tmp_delete_team_member.json" ".detail" "Cannot remove the account owner" "Error detail"
    
    print_test_success
}

# Step 23: Invite Existing Team Member (Should Fail)
test_step_23_invite_existing_team_member() {
    print_step "Invite Existing Team Member (Should Fail)"

    local request="curl -s -w '%{http_code}' -o tmp_invite_existing_member.json -X POST -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' -H 'Content-Type: application/json' '$API_URL/team_members/invite' -d '{\"email\":\"$CUSTOMER1_EMAIL\",\"role\":\"admin\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_invite_existing_member.json \
        -X POST \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL/team_members/invite" \
        -d "{\"email\":\"$CUSTOMER1_EMAIL\",\"role\":\"admin\"}")
    print_debug_response "$response" "tmp_invite_existing_member.json"

    check_response "$response" "400" "Invite existing team member"
    validate_json_field "tmp_invite_existing_member.json" ".detail" "User is already a team member" "Error detail"

    print_test_success
}

# Step 24: Invite Existing User as New Team Member
test_step_24_invite_existing_user_new_team_member() {
    print_step "Invite Existing User as New Team Member"

    local request="curl -s -w '%{http_code}' -o tmp_invite_new_member.json -X POST -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' -H 'Content-Type: application/json' '$API_URL/team_members/invite' -d '{\"email\":\"$NEW_TEAM_MEMBER_EMAIL\",\"role\":\"admin\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_invite_new_member.json \
        -X POST \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL/team_members/invite" \
        -d "{\"email\":\"$NEW_TEAM_MEMBER_EMAIL\",\"role\":\"admin\"}")
    print_debug_response "$response" "tmp_invite_new_member.json"

    check_response_any "$response" "Invite existing user as new team member" "200" "201"
    validate_json_field "tmp_invite_new_member.json" ".email" "$NEW_TEAM_MEMBER_EMAIL" "Invitation email"
    validate_json_field "tmp_invite_new_member.json" ".status" "invited" "Invitation status"
    validate_json_field "tmp_invite_new_member.json" ".message" "Invitation sent successfully" "Invitation message"
    validate_boolean "tmp_invite_new_member.json" ".user_exists" "true" "User exists flag"

    print_test_success
}

# Step 25: Get All Team Members After Invite
test_step_25_get_team_members_after_invite() {
    print_step "Get All Team Members After Invite"

    local request="curl -s -w '%{http_code}' -o tmp_team_members_after_invite.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_team_members_after_invite.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members")
    print_debug_response "$response" "tmp_team_members_after_invite.json"

    check_response "$response" "200" "Get team members after invite"
    validate_json_field "tmp_team_members_after_invite.json" ".items | length" "2" "Team members count after invite"
    validate_json_field "tmp_team_members_after_invite.json" ".items | map(select(.role==\"admin\" and .status==\"invited\")) | .[0].role" "admin" "Invited member role"
    validate_json_field "tmp_team_members_after_invite.json" ".items | map(select(.role==\"admin\" and .status==\"invited\")) | .[0].status" "invited" "Invited member status"
    validate_json_field "tmp_team_members_after_invite.json" ".items | map(select(.role==\"admin\" and .status==\"invited\")) | .[0].name" "$NEW_TEAM_MEMBER_NAME" "Invited member name"

    print_test_success
}

# Step 26: Sign In Invited Team Member
test_step_26_signin_invited_team_member() {
    print_step "Sign In Invited Team Member"

    local request="curl -s -w '%{http_code}' -o tmp_invited_member_signin.json -X POST '$API_URL/signin' -H 'Content-Type: application/json' -d '{\"email\": \"$NEW_TEAM_MEMBER_EMAIL\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_invited_member_signin.json -X POST "$API_URL/signin" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$NEW_TEAM_MEMBER_EMAIL\"}")
    print_debug_response "$response" "tmp_invited_member_signin.json"

    check_response "$response" "201" "Sign in invited team member"
    validate_json_not_null "tmp_invited_member_signin.json" ".token" "Invited member magic token"
    validate_json_not_null "tmp_invited_member_signin.json" ".expires_at" "Invited member token expiration"

    NEW_TEAM_MEMBER_MAGIC_TOKEN=$(jq -r '.token' tmp_invited_member_signin.json)
    print_debug "Saved invited member magic token: $NEW_TEAM_MEMBER_MAGIC_TOKEN"

    print_test_success
}

# Step 27: Confirm Sign In Invited Team Member
test_step_27_confirm_signin_invited_team_member() {
    print_step "Confirm Sign In Invited Team Member"

    local request="curl -s -w '%{http_code}' -o tmp_invited_member_confirm.json -X POST '$API_URL/signin/confirm' -H 'Content-Type: application/json' -d '{\"email\": \"$NEW_TEAM_MEMBER_EMAIL\", \"token\": \"$NEW_TEAM_MEMBER_MAGIC_TOKEN\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_invited_member_confirm.json -X POST "$API_URL/signin/confirm" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$NEW_TEAM_MEMBER_EMAIL\", \"token\": \"$NEW_TEAM_MEMBER_MAGIC_TOKEN\"}")
    print_debug_response "$response" "tmp_invited_member_confirm.json"

    check_response "$response" "200" "Confirm invited team member sign in"
    validate_json_not_null "tmp_invited_member_confirm.json" ".access_token" "Invited member access token"
    validate_json_not_null "tmp_invited_member_confirm.json" ".token_type" "Invited member token type"
    validate_json_field "tmp_invited_member_confirm.json" ".user.email" "$NEW_TEAM_MEMBER_EMAIL" "Invited member email"
    validate_json_field "tmp_invited_member_confirm.json" ".user.name" "$NEW_TEAM_MEMBER_NAME" "Invited member name"
    validate_json_field "tmp_invited_member_confirm.json" ".user.team_member_status" "accepted" "Invited member status"

    NEW_TEAM_MEMBER_ACCESS_TOKEN=$(jq -r '.access_token' tmp_invited_member_confirm.json)
    print_debug "Saved invited member access token"

    print_test_success
}

# Step 28: Get All Team Members After Invite Acceptance
test_step_28_get_team_members_after_acceptance() {
    print_step "Get All Team Members After Invite Acceptance"

    local request="curl -s -w '%{http_code}' -o tmp_team_members_after_acceptance.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_team_members_after_acceptance.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members")
    print_debug_response "$response" "tmp_team_members_after_acceptance.json"

    check_response "$response" "200" "Get team members after invite acceptance"
    validate_json_field "tmp_team_members_after_acceptance.json" ".items | length" "2" "Team members count after acceptance"
    validate_json_field "tmp_team_members_after_acceptance.json" ".items | map(select(.role==\"admin\" and .name==\"$NEW_TEAM_MEMBER_NAME\")) | .[0].status" "accepted" "Accepted member status"
    validate_json_field "tmp_team_members_after_acceptance.json" ".items | map(select(.role==\"admin\" and .name==\"$NEW_TEAM_MEMBER_NAME\")) | .[0].name" "$NEW_TEAM_MEMBER_NAME" "Accepted member name"

    print_test_success
}

# Step 29: Get Notifications After Invite Acceptance
test_step_29_get_notifications_after_invite_acceptance() {
    print_step "Get Notifications After Invite Acceptance"

    local request="curl -s -w '%{http_code}' -o tmp_notifications_after_acceptance.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_notifications_after_acceptance.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications")
    print_debug_response "$response" "tmp_notifications_after_acceptance.json"

    check_response "$response" "200" "Get notifications after invite acceptance"
    validate_json_field "tmp_notifications_after_acceptance.json" ".items | length" "2" "Notifications count after invite acceptance"
    validate_json_field "tmp_notifications_after_acceptance.json" ".items | sort_by(.created_at) | reverse | .[0].subject" "microsaas.farm+1 accepted your invitation to fastapi-starter-kit" "Latest notification subject after invite acceptance"
    validate_json_field "tmp_notifications_after_acceptance.json" ".items | sort_by(.created_at) | reverse | .[0].body" "microsaas.farm+1 (microsaas.farm+1@gmail.com) accepted your invitation to join microsaas.farm's Account on fastapi-starter-kit." "Latest notification body after invite acceptance"
    validate_json_field "tmp_notifications_after_acceptance.json" ".items | sort_by(.created_at) | reverse | .[0].type" "invite_accepted" "Latest notification type after invite acceptance"
    validate_boolean "tmp_notifications_after_acceptance.json" ".items | sort_by(.created_at) | reverse | .[0].is_read" "false" "Latest notification is unread after invite acceptance"
    validate_json_not_null "tmp_notifications_after_acceptance.json" ".items | sort_by(.created_at) | reverse | .[0].id" "Invite accepted notification id"

    INVITE_ACCEPTED_NOTIFICATION_ID=$(jq -r '.items | sort_by(.created_at) | reverse | .[0].id' tmp_notifications_after_acceptance.json)
    print_debug "Saved invite accepted notification ID: $INVITE_ACCEPTED_NOTIFICATION_ID"

    print_test_success
}

# Step 30: Filter Notifications After Invite Acceptance
test_step_30_filter_notifications_after_invite_acceptance() {
    print_step "Filter Notifications After Invite Acceptance"

    local request_unread_zero="curl -s -w '%{http_code}' -o tmp_notifications_filter_acceptance_zero.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications?is_read=0'"
    print_debug_request "$request_unread_zero"

    local response_unread_zero=$(curl -s -w "%{http_code}" -o tmp_notifications_filter_acceptance_zero.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications?is_read=0")
    print_debug_response "$response_unread_zero" "tmp_notifications_filter_acceptance_zero.json"

    check_response "$response_unread_zero" "200" "Get notifications with numeric is_read=0 after invite acceptance"
    validate_json_field "tmp_notifications_filter_acceptance_zero.json" ".items | length" "1" "Notifications count with is_read=0 filter after invite acceptance"

    local request_unread_false="curl -s -w '%{http_code}' -o tmp_notifications_filter_acceptance_false.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications?is_read=false'"
    print_debug_request "$request_unread_false"

    local response_unread_false=$(curl -s -w "%{http_code}" -o tmp_notifications_filter_acceptance_false.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications?is_read=false")
    print_debug_response "$response_unread_false" "tmp_notifications_filter_acceptance_false.json"

    check_response "$response_unread_false" "200" "Get notifications with boolean false filter after invite acceptance"
    validate_json_field "tmp_notifications_filter_acceptance_false.json" ".items | length" "1" "Notifications count with is_read=false filter after invite acceptance"

    local request_read_true="curl -s -w '%{http_code}' -o tmp_notifications_filter_acceptance_true.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications?is_read=1'"
    print_debug_request "$request_read_true"

    local response_read_true=$(curl -s -w "%{http_code}" -o tmp_notifications_filter_acceptance_true.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications?is_read=1")
    print_debug_response "$response_read_true" "tmp_notifications_filter_acceptance_true.json"

    check_response "$response_read_true" "200" "Get notifications with is_read=1 filter after invite acceptance"
    validate_json_field "tmp_notifications_filter_acceptance_true.json" ".items | length" "1" "Notifications count with is_read=1 filter after invite acceptance"

    local request_count_all="curl -s -w '%{http_code}' -o tmp_notification_count_after_acceptance.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count'"
    print_debug_request "$request_count_all"

    local response_count_all=$(curl -s -w "%{http_code}" -o tmp_notification_count_after_acceptance.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count")
    print_debug_response "$response_count_all" "tmp_notification_count_after_acceptance.json"

    check_response "$response_count_all" "200" "Get notification count after invite acceptance"
    validate_json_field "tmp_notification_count_after_acceptance.json" ".count" "2" "Notification count after invite acceptance"

    local request_count_unread="curl -s -w '%{http_code}' -o tmp_notification_count_unread_after_acceptance.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count?is_read=0'"
    print_debug_request "$request_count_unread"

    local response_count_unread=$(curl -s -w "%{http_code}" -o tmp_notification_count_unread_after_acceptance.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count?is_read=0")
    print_debug_response "$response_count_unread" "tmp_notification_count_unread_after_acceptance.json"

    check_response "$response_count_unread" "200" "Get unread notification count after invite acceptance"
    validate_json_field "tmp_notification_count_unread_after_acceptance.json" ".count" "1" "Unread notification count after invite acceptance"

    local request_count_read="curl -s -w '%{http_code}' -o tmp_notification_count_read_after_acceptance.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/count?is_read=1'"
    print_debug_request "$request_count_read"

    local response_count_read=$(curl -s -w "%{http_code}" -o tmp_notification_count_read_after_acceptance.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/count?is_read=1")
    print_debug_response "$response_count_read" "tmp_notification_count_read_after_acceptance.json"

    check_response "$response_count_read" "200" "Get read notification count after invite acceptance"
    validate_json_field "tmp_notification_count_read_after_acceptance.json" ".count" "1" "Read notification count after invite acceptance"

    print_test_success
}

# Step 31: Mark Invite Accepted Notification as Read
test_step_31_mark_invite_notification_as_read() {
    print_step "Mark Invite Accepted Notification as Read"

    local request="curl -s -w '%{http_code}' -o tmp_invite_notification_read.json -X POST -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications/$INVITE_ACCEPTED_NOTIFICATION_ID/read'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_invite_notification_read.json \
        -X POST \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications/$INVITE_ACCEPTED_NOTIFICATION_ID/read")
    print_debug_response "$response" "tmp_invite_notification_read.json"

    check_response "$response" "200" "Mark invite accepted notification as read"
    validate_json_field "tmp_invite_notification_read.json" ".subject" "microsaas.farm+1 accepted your invitation to fastapi-starter-kit" "Invite accepted notification subject"
    validate_boolean "tmp_invite_notification_read.json" ".is_read" "true" "Invite accepted notification is read"

    print_test_success
}

# Step 32: Get Team Members After Acceptance and Save Admin Member ID
test_step_32_get_admin_team_member_id() {
    print_step "Get Team Members After Acceptance and Save Admin Member ID"

    local request="curl -s -w '%{http_code}' -o tmp_team_members_after_acceptance_save.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_team_members_after_acceptance_save.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members")
    print_debug_response "$response" "tmp_team_members_after_acceptance_save.json"

    check_response "$response" "200" "Get team members to save admin ID"
    validate_json_field "tmp_team_members_after_acceptance_save.json" ".items | length" "2" "Team members count when saving admin ID"
    validate_json_field "tmp_team_members_after_acceptance_save.json" ".items | map(select(.role==\"admin\" and .name==\"$NEW_TEAM_MEMBER_NAME\")) | .[0].status" "accepted" "Admin member status before update"

    ADMIN_TEAM_MEMBER_ID=$(jq -r ".items | map(select(.role==\"admin\" and .name==\"$NEW_TEAM_MEMBER_NAME\")) | .[0].id" tmp_team_members_after_acceptance_save.json)
    if [[ -z "$ADMIN_TEAM_MEMBER_ID" || "$ADMIN_TEAM_MEMBER_ID" == "null" ]]; then
        print_error "Failed to save admin team member ID"
        exit 1
    fi
    print_debug "Saved admin team member ID: $ADMIN_TEAM_MEMBER_ID"

    print_test_success
}

# Step 33: Update Admin Team Member Role to Guest
test_step_33_update_team_member_role_to_guest() {
    print_step "Update Admin Team Member Role to Guest"

    if [[ -z "$ADMIN_TEAM_MEMBER_ID" ]]; then
        print_error "Admin team member ID is not set"
        exit 1
    fi

    local request="curl -s -w '%{http_code}' -o tmp_update_admin_team_member.json -X PATCH -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' -H 'Content-Type: application/json' '$API_URL/team_members/$ADMIN_TEAM_MEMBER_ID' -d '{\"role\":\"guest\"}'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_update_admin_team_member.json \
        -X PATCH \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL/team_members/$ADMIN_TEAM_MEMBER_ID" \
        -d '{"role":"guest"}')
    print_debug_response "$response" "tmp_update_admin_team_member.json"

    check_response "$response" "200" "Update team member role to guest"
    validate_json_field "tmp_update_admin_team_member.json" ".message" "Team member updated successfully" "Update team member message"
    validate_json_field "tmp_update_admin_team_member.json" ".id" "$ADMIN_TEAM_MEMBER_ID" "Updated team member ID"
    validate_json_field "tmp_update_admin_team_member.json" ".role" "guest" "Updated team member role"
    validate_json_field "tmp_update_admin_team_member.json" ".status" "accepted" "Updated team member status"

    print_test_success
}

# Step 34: Delete Updated Team Member
test_step_34_delete_guest_team_member() {
    print_step "Delete Updated Team Member"

    if [[ -z "$ADMIN_TEAM_MEMBER_ID" ]]; then
        print_error "Admin team member ID is not set"
        exit 1
    fi

    local request="curl -s -w '%{http_code}' -o tmp_delete_admin_team_member.json -X DELETE -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members/$ADMIN_TEAM_MEMBER_ID'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_delete_admin_team_member.json \
        -X DELETE \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members/$ADMIN_TEAM_MEMBER_ID")
    print_debug_response "$response" "tmp_delete_admin_team_member.json"

    check_response "$response" "200" "Delete updated team member"
    validate_json_field "tmp_delete_admin_team_member.json" ".message" "Team member removed successfully" "Delete team member message"
    validate_json_field "tmp_delete_admin_team_member.json" ".id" "$ADMIN_TEAM_MEMBER_ID" "Deleted team member ID"

    print_test_success
}

# Step 35: Get Team Members After Deleting Updated Member
test_step_35_get_team_members_after_delete() {
    print_step "Get Team Members After Deleting Updated Member"

    local request="curl -s -w '%{http_code}' -o tmp_team_members_after_delete.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/team_members'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_team_members_after_delete.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/team_members")
    print_debug_response "$response" "tmp_team_members_after_delete.json"

    check_response "$response" "200" "Get team members after deleting updated member"
    validate_json_field "tmp_team_members_after_delete.json" ".items | length" "1" "Team members count after delete"

    local remaining_matches=$(jq ".items | map(select(.id==\"$ADMIN_TEAM_MEMBER_ID\")) | length" tmp_team_members_after_delete.json)
    if [[ "$remaining_matches" != "0" ]]; then
        print_error "Deleted team member still present in team members list"
        exit 1
    else
        print_success "Deleted team member is not present in team members list"
    fi

    print_test_success
}

# Step 36: Get Notifications After Marking Invite Acceptance as Read
test_step_36_get_notifications_after_mark_read() {
    print_step "Get Notifications After Marking Invite Acceptance as Read"

    local request="curl -s -w '%{http_code}' -o tmp_notifications_after_read.json -H 'Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN' '$API_URL/notifications'"
    print_debug_request "$request"

    local response=$(curl -s -w "%{http_code}" -o tmp_notifications_after_read.json \
        -H "Authorization: Bearer $CUSTOMER1_ACCESS_TOKEN" \
        "$API_URL/notifications")
    print_debug_response "$response" "tmp_notifications_after_read.json"

    check_response "$response" "200" "Get notifications after marking invite acceptance as read"
    validate_json_field "tmp_notifications_after_read.json" ".items | length" "2" "Notifications count after marking invite acceptance as read"
    validate_boolean "tmp_notifications_after_read.json" ".items | map(select(.id==\"$INVITE_ACCEPTED_NOTIFICATION_ID\")) | .[0].is_read" "true" "Invite accepted notification is read in list"

    print_test_success
}

# ============================================================================
# Parse Arguments
# ============================================================================

parse_arguments() {
    for arg in "$@"; do
        case $arg in
            --clean-db)
                CLEAN_DB=true
                shift
                ;;
            --debug)
                DEBUG=true
                shift
                ;;
            --help)
                head -n 14 "$0" | tail -n 12
                exit 0
                ;;
            *)
                echo "Unknown option: $arg"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    parse_arguments "$@"
    
    print_header "E2E TESTING SCRIPT - COMPLETE WORKFLOW"
    echo "Base URL: $BASE_URL"
    echo "API URL: $API_URL"
    echo "Customer Email: $CUSTOMER1_EMAIL"
    echo "Clean DB: $CLEAN_DB"
    echo "Debug: $DEBUG"
    
    cleanup_temp_files
    clean_database
    
    # Run all test steps
    test_step_1_server_ping
    test_step_2_signin_new_customer
    test_step_3_confirm_wrong_email
    test_step_4_confirm_wrong_token
    test_step_5_confirm_signin
    test_step_6_confirm_again
    test_step_7_get_current_user
    test_step_8_update_current_user
    test_step_9_get_current_user_after_update
    test_step_10_get_notifications
    test_step_11_get_unread_notifications_with_filter
    test_step_12_get_read_notifications_with_filter
    test_step_13_get_notification_count
    test_step_14_get_unread_notification_count
    test_step_15_get_read_notification_count
    test_step_16_read_notifications
    test_step_17_get_notifications_again
    test_step_18_get_notification_by_id
    test_step_19_get_team_members
    test_step_20_get_team_member_by_id
    test_step_21_update_team_member
    test_step_22_delete_team_member
    test_step_23_invite_existing_team_member
    test_step_24_invite_existing_user_new_team_member
    test_step_25_get_team_members_after_invite
    test_step_26_signin_invited_team_member
    test_step_27_confirm_signin_invited_team_member
    test_step_28_get_team_members_after_acceptance
    test_step_29_get_notifications_after_invite_acceptance
    test_step_30_filter_notifications_after_invite_acceptance
    test_step_31_mark_invite_notification_as_read
    test_step_32_get_admin_team_member_id
    test_step_33_update_team_member_role_to_guest
    test_step_34_delete_guest_team_member
    test_step_35_get_team_members_after_delete
    test_step_36_get_notifications_after_mark_read
    
    # Print Summary
    print_header "TEST SUMMARY"
    echo "Total Test Steps: $CURRENT_TEST"
    echo "Total Assertions: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo ""
        echo "================================================================"
        echo -e "${GREEN}  ✅ ALL TESTS PASSED SUCCESSFULLY! 🎉${NC}"
        echo "================================================================"
    else
        echo ""
        echo "================================================================"
        echo -e "${RED}  ❌ SOME TESTS FAILED${NC}"
        echo "================================================================"
        exit 1
    fi
    
    cleanup_temp_files
}

# Run main function
main "$@"
