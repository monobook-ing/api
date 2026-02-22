# Magic Link Authentication Implementation

## Overview

This implementation provides a complete passwordless authentication flow using magic links. When a user confirms their magic link, the system automatically:

1. Validates the token
2. Creates a new user (if they don't exist)
3. Creates a default workspace/account for the user
4. Adds the user as an OWNER of their account via team_members table
5. Returns a JWT token for immediate authentication

## Database Schema

Run the SQL migration script to create the required tables:

```bash
# Execute the migration in your Supabase SQL editor
# or via CLI. This also syncs recent changes such as the notification_type enum
# and notification details/cta columns:
supabase db push
```

### Tables Created:
- **users**: Stores user information
- **accounts**: Stores workspace/account information
- **team_members**: Links users to accounts with roles
- **magic_tokens**: Stores magic link tokens

## API Endpoints

### 1. Request Magic Link

**POST** `/v1.0/signin`

Request a magic link to be sent to the user's email.

```json
// Request
{
  "email": "microsaas.farm@gmail.com"
}

// Response (201 Created)
{
  "token": "b0cfbda7-68a5-4331-a47b-e7de0310a02a",
  "expires_at": "2025-12-25T15:00:00Z"
}
```

### 2. Confirm Magic Link

**POST** `/v1.0/signin/confirm`

Verify the magic link token and authenticate the user.

```json
// Request
{
  "email": "microsaas.farm@gmail.com",
  "token": "b0cfbda7-68a5-4331-a47b-e7de0310a02a"
}

// Response (200 OK)
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_at": "2026-01-15T14:09:53.119669Z",
  "user": {
    "id": "af2a103b-1e52-457a-af33-c5b2f9c4e2e3",
    "email": "microsaas.farm@gmail.com",
    "name": "microsaas.farm",
    "role": "USER",
    "status": "ACTIVE",
    "is_guest": false
  }
}
```

## Error Responses

### Invalid Token
```json
{
  "detail": "Invalid or expired token"
}
```

### Token Mismatch
```json
{
  "detail": "Token does not match the provided email"
}
```

### Token Already Used
```json
{
  "detail": "Token has already been used"
}
```

### Expired Token
```json
{
  "detail": "Token has expired"
}
```

## Business Logic Flow

### For New Users:
1. Verify token exists and is valid
2. Check token matches the provided email
3. Verify token hasn't been used
4. Verify token hasn't expired
5. Create new user record
6. Create default account with name "{username}'s Workspace"
7. Create team_member record with OWNER role
8. Mark token as used
9. Generate JWT token
10. Return authentication response

### For Existing Users:
1. Verify token exists and is valid
2. Check token matches the provided email
3. Verify token hasn't been used
4. Verify token hasn't expired
5. Retrieve existing user
6. Mark token as used
7. Generate JWT token
8. Return authentication response

## Configuration

Ensure your `.env` file contains:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key

# JWT
JWT_SECRET=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Email (optional, for sending magic links)
RESEND_API_KEY=your-resend-key
RESEND_FROM_EMAIL=noreply@yourdomain.com
MAGIC_LINK_BASE_URL=https://yourapp.com/auth/verify?token={token}
```

## Testing

### Using curl:

```bash
# 1. Request magic link
curl -X POST http://localhost:8000/v1.0/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# 2. Confirm magic link
curl -X POST http://localhost:8000/v1.0/signin/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "token": "b0cfbda7-68a5-4331-a47b-e7de0310a02a"
  }'
```

### Using Python:

```python
import httpx

# Request magic link
response = httpx.post(
    "http://localhost:8000/v1.0/signin",
    json={"email": "test@example.com"}
)
token_data = response.json()
print(f"Token: {token_data['token']}")

# Confirm magic link
response = httpx.post(
    "http://localhost:8000/v1.0/signin/confirm",
    json={
        "email": "test@example.com",
        "token": token_data["token"]
    }
)
auth_data = response.json()
print(f"Access Token: {auth_data['access_token']}")
```

## Security Considerations

1. **Token Expiration**: Tokens expire after 15 minutes by default
2. **One-time Use**: Tokens can only be used once
3. **Email Verification**: Token must match the email it was issued to
4. **JWT Security**: Use a strong JWT_SECRET in production
5. **HTTPS**: Always use HTTPS in production
6. **CORS**: Configure CORS properly for your frontend domain

## Frontend Integration

```typescript
// Step 1: Request magic link
async function requestMagicLink(email: string) {
  const response = await fetch('/v1.0/signin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  return response.json();
}

// Step 2: Confirm magic link (from email link)
async function confirmMagicLink(email: string, token: string) {
  const response = await fetch('/v1.0/signin/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, token })
  });
  
  const data = await response.json();
  
  // Store the JWT token
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('user', JSON.stringify(data.user));
  
  return data;
}

// Step 3: Use the token for authenticated requests
async function fetchProtectedData() {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('/protected/me', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  return response.json();
}
```

## Database Relationships

```
users (1) ──< team_members (many) >── (1) accounts
  │                                        │
  │                                        │
  └─────────────< magic_tokens            └─ owner_id references users
```

- A user can belong to multiple accounts via team_members
- Each account has one owner (user)
- Each user automatically gets a default account when created
- Magic tokens can reference a user (if they exist) or just an email

## Troubleshooting

### Token Not Found
- Ensure the token exists in the database
- Check token hasn't been cleaned up by expired token deletion

### User Creation Failed
- Verify Supabase service key has proper permissions
- Check database constraints and indexes
- Review Supabase logs for detailed errors

### JWT Token Invalid
- Verify JWT_SECRET is consistent
- Check token expiration settings
- Ensure clock synchronization on server
