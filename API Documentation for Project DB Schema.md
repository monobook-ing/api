# Pixel Perfect Admin - API Documentation

## Overview

This document provides comprehensive API endpoint documentation for the Pixel Perfect Admin platform. All endpoints follow RESTful conventions and use JSON for request/response bodies.

### Base URL
```
https://api.pixelperfect.app/v1
```

### Authentication
All endpoints (except auth endpoints) require a Bearer token in the Authorization header:
```
Authorization: Bearer <access_token>
```

### Common Response Format
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 100,
    "totalPages": 5
  }
}
```

### Error Response Format
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Brief is required",
    "details": [
      { "field": "brief", "message": "Brief cannot be empty" }
    ]
  }
}
```

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Users](#2-users)
3. [Accounts & Teams](#3-accounts--teams)
4. [Creator Profiles](#4-creator-profiles)
5. [Brand Profiles](#5-brand-profiles)
6. [Requests](#6-requests)
7. [Projects](#7-projects)
8. [Deliverables](#8-deliverables)
9. [Quotes](#9-quotes)
10. [Messages](#10-messages)
11. [Favorites](#11-favorites)
12. [Reviews](#12-reviews)
13. [Portfolio](#13-portfolio)
14. [Files](#14-files)
15. [Notifications](#15-notifications)
16. [Billing](#16-billing)
17. [Admin](#17-admin)

---

## 1. Authentication

### POST /auth/magic-link
Send a magic link to the user's email for passwordless authentication.

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Magic link sent to user@example.com",
    "expiresIn": 600
  }
}
```

---

### POST /auth/magic-link/verify
Verify the magic link token and return access token.

**Request:**
```json
{
  "token": "abc123xyz..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "dGhpcyBpcyBhIHJlZnJlc2g...",
    "expiresIn": 86400,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "firstName": "John",
      "lastName": "Doe",
      "role": "brand"
    }
  }
}
```

---

### POST /auth/google
Authenticate with Google OAuth.

**Request:**
```json
{
  "idToken": "google_id_token..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "dGhpcyBpcyBhIHJlZnJlc2g...",
    "expiresIn": 86400,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "firstName": "John",
      "lastName": "Doe",
      "role": "brand"
    },
    "isNewUser": false
  }
}
```

---

### POST /auth/refresh
Refresh the access token.

**Request:**
```json
{
  "refreshToken": "dGhpcyBpcyBhIHJlZnJlc2g..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "expiresIn": 86400
  }
}
```

---

### POST /auth/logout
Invalidate the current session.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Successfully logged out"
  }
}
```

---

## 2. Users

### GET /users/me
Get the current authenticated user.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Doe",
    "role": "brand",
    "createdAt": "2024-01-15T10:30:00Z",
    "account": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "Acme Corp"
    },
    "preferences": {
      "theme": "dark",
      "language": "en",
      "timezone": "America/New_York"
    }
  }
}
```

---

### PATCH /users/me
Update the current user's profile.

**Request:**
```json
{
  "firstName": "John",
  "lastName": "Smith"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Smith",
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### PATCH /users/me/preferences
Update user preferences.

**Request:**
```json
{
  "theme": "dark",
  "language": "en",
  "timezone": "America/New_York"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "theme": "dark",
    "language": "en",
    "timezone": "America/New_York",
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### DELETE /users/me
Delete the current user's account.

**Request:**
```json
{
  "confirmEmail": "user@example.com"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Account scheduled for deletion"
  }
}
```

---

## 3. Accounts & Teams

### GET /accounts/current
Get the current account details.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Acme Corp",
    "isDefault": true,
    "memberCount": 5,
    "createdAt": "2024-01-01T00:00:00Z"
  }
}
```

---

### PATCH /accounts/current
Update the current account.

**Request:**
```json
{
  "name": "Acme Corporation"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Acme Corporation",
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### GET /accounts/current/members
List all team members.

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "user": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "john@acme.com",
        "firstName": "John",
        "lastName": "Doe"
      },
      "role": "admin",
      "status": "accepted",
      "joinedAt": "2024-01-01T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 5
  }
}
```

---

### POST /accounts/current/members/invite
Invite a new team member.

**Request:**
```json
{
  "email": "newmember@example.com",
  "role": "admin"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "880e8400-e29b-41d4-a716-446655440003",
    "email": "newmember@example.com",
    "role": "admin",
    "status": "invited",
    "invitedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### DELETE /accounts/current/members/:memberId
Remove a team member.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Team member removed successfully"
  }
}
```

---

### PATCH /accounts/current/members/:memberId/role
Update a team member's role.

**Request:**
```json
{
  "role": "brand"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "role": "brand",
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

## 4. Creator Profiles

### GET /creators
List all creators (public discovery).

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)
- `search` (optional): Search by name or specialty
- `specialty` (optional): Filter by specialty
- `minRating` (optional): Minimum rating filter
- `available` (optional): Filter by availability (true/false)
- `sortBy` (optional): Sort field (rating, reviewCount, projectsCompleted)
- `sortOrder` (optional): asc or desc

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "userId": "550e8400-e29b-41d4-a716-446655440000",
      "user": {
        "firstName": "Alex",
        "lastName": "Kim"
      },
      "specialty": "3D Art",
      "location": "Los Angeles, CA",
      "rating": 4.9,
      "reviewCount": 47,
      "projectsCompleted": 89,
      "isAvailable": true,
      "avatar": "https://example.com/avatars/alex.jpg",
      "coverImage": "https://example.com/covers/alex.jpg",
      "skills": ["3D Modeling", "Product Viz", "Motion Graphics"]
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 150
  }
}
```

---

### GET /creators/:id
Get a specific creator's public profile.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "userId": "550e8400-e29b-41d4-a716-446655440000",
    "user": {
      "firstName": "Alex",
      "lastName": "Kim"
    },
    "specialty": "3D Art",
    "bio": "Award-winning 3D artist specializing in product visualization...",
    "location": "Los Angeles, CA",
    "memberSince": "2023-01-15",
    "rating": 4.9,
    "reviewCount": 47,
    "projectsCompleted": 89,
    "repeatClients": 34,
    "avgResponseTimeMinutes": 120,
    "isAvailable": true,
    "avatar": "https://example.com/avatars/alex.jpg",
    "coverImage": "https://example.com/covers/alex.jpg",
    "skills": ["3D Modeling", "Product Viz", "Motion Graphics", "Blender", "Cinema 4D"],
    "portfolio": [
      {
        "id": "aa0e8400-e29b-41d4-a716-446655440005",
        "title": "Abstract Flow",
        "imageUrl": "https://example.com/portfolio/1.jpg"
      }
    ],
    "recentReviews": [
      {
        "id": "bb0e8400-e29b-41d4-a716-446655440006",
        "rating": 5,
        "content": "Excellent work!",
        "reviewer": {
          "firstName": "Sarah",
          "lastName": "M."
        },
        "createdAt": "2024-01-15T00:00:00Z"
      }
    ]
  }
}
```

---

### GET /creators/me
Get the current user's creator profile (for creators).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "specialty": "3D Art",
    "bio": "Award-winning 3D artist...",
    "location": "Los Angeles, CA",
    "rating": 4.9,
    "reviewCount": 47,
    "projectsCompleted": 89,
    "repeatClients": 34,
    "balance": 2500.00,
    "isAvailable": true,
    "skills": ["3D Modeling", "Product Viz", "Motion Graphics"]
  }
}
```

---

### PATCH /creators/me
Update the current user's creator profile.

**Request:**
```json
{
  "specialty": "3D Art & Animation",
  "bio": "Updated bio...",
  "location": "San Francisco, CA",
  "isAvailable": true
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "specialty": "3D Art & Animation",
    "bio": "Updated bio...",
    "location": "San Francisco, CA",
    "isAvailable": true,
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### PUT /creators/me/skills
Update creator skills.

**Request:**
```json
{
  "skills": ["3D Modeling", "Product Viz", "Motion Graphics", "Blender", "Cinema 4D", "After Effects"]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "skills": ["3D Modeling", "Product Viz", "Motion Graphics", "Blender", "Cinema 4D", "After Effects"],
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

### GET /creators/worked-with
Get creators the current user has worked with.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "user": {
        "firstName": "Sarah",
        "lastName": "Chen"
      },
      "avatar": "https://example.com/avatars/sarah.jpg",
      "specialty": "Photography",
      "collaborationCount": 5
    }
  ]
}
```

---

## 5. Brand Profiles

### GET /brands/me
Get the current account's brand profile.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "cc0e8400-e29b-41d4-a716-446655440007",
    "accountId": "660e8400-e29b-41d4-a716-446655440001",
    "companyName": "Acme Corp",
    "companyEmail": "contact@acme.com",
    "companyWebsite": "https://acme.com",
    "companyLogo": "https://example.com/logos/acme.png",
    "industry": "Technology",
    "subscriptionPlan": "pro",
    "subscriptionExpiresAt": "2025-01-01T00:00:00Z",
    "totalRequests": 45
  }
}
```

---

### PATCH /brands/me
Update the brand profile.

**Request:**
```json
{
  "companyName": "Acme Corporation",
  "companyEmail": "hello@acme.com",
  "companyWebsite": "https://acmecorp.com",
  "industry": "Enterprise Technology"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "cc0e8400-e29b-41d4-a716-446655440007",
    "companyName": "Acme Corporation",
    "companyEmail": "hello@acme.com",
    "companyWebsite": "https://acmecorp.com",
    "industry": "Enterprise Technology",
    "updatedAt": "2024-01-20T14:00:00Z"
  }
}
```

---

## 6. Requests

### GET /requests
List all requests for the current account/creator.

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)
- `status` (optional): Filter by status (created, submitted, in_progress, approved, rejected)
- `type` (optional): Filter by content type (image, video)
- `search` (optional): Search by request ID
- `sortBy` (optional): Sort field (createdAt, budget, deadline)
- `sortOrder` (optional): asc or desc

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "dd0e8400-e29b-41d4-a716-446655440008",
      "contentType": "image",
      "brief": "Need a hero banner for our new SaaS product launch...",
      "toneOfVoice": "professional",
      "budget": 250.00,
      "deadline": "2024-02-15",
      "status": "submitted",
      "createdAt": "2024-01-20T10:00:00Z",
      "creator": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "firstName": "Maria",
        "lastName": "Santos"
      }
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 12
  }
}
```

---

### POST /requests
Create a new content request.

**Request:**
```json
{
  "contentType": "image",
  "brief": "Need a hero banner for our new SaaS product launch. Modern, clean, with abstract tech elements.",
  "toneOfVoice": "professional",
  "budget": 250.00,
  "deadline": "2024-02-15"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "contentType": "image",
    "brief": "Need a hero banner for our new SaaS product launch...",
    "toneOfVoice": "professional",
    "budget": 250.00,
    "deadline": "2024-02-15",
    "status": "created",
    "createdAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### GET /requests/:id
Get a specific request.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "contentType": "image",
    "brief": "Need a hero banner for our new SaaS product launch...",
    "toneOfVoice": "professional",
    "budget": 250.00,
    "deadline": "2024-02-15",
    "status": "in_progress",
    "statusChangedAt": "2024-01-21T14:00:00Z",
    "createdAt": "2024-01-20T10:00:00Z",
    "createdBy": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "John",
      "lastName": "Doe"
    },
    "assignedCreator": {
      "id": "ee0e8400-e29b-41d4-a716-446655440009",
      "firstName": "Maria",
      "lastName": "Santos"
    },
    "deliverables": [
      {
        "id": "ff0e8400-e29b-41d4-a716-446655440010",
        "name": "hero-banner-final.png",
        "status": "submitted",
        "submittedAt": "2024-01-25T10:00:00Z"
      }
    ],
    "messages": [
      {
        "id": "gg0e8400-e29b-41d4-a716-446655440011",
        "content": "Hi! Looking forward to working with you.",
        "sender": {
          "id": "550e8400-e29b-41d4-a716-446655440000",
          "firstName": "John"
        },
        "createdAt": "2024-01-20T11:00:00Z"
      }
    ]
  }
}
```

---

### PATCH /requests/:id
Update a request (only certain fields based on status).

**Request:**
```json
{
  "brief": "Updated brief...",
  "budget": 300.00,
  "deadline": "2024-02-20"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "brief": "Updated brief...",
    "budget": 300.00,
    "deadline": "2024-02-20",
    "updatedAt": "2024-01-20T15:00:00Z"
  }
}
```

---

### POST /requests/:id/submit
Submit a request to find creators.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "status": "submitted",
    "statusChangedAt": "2024-01-20T15:00:00Z"
  }
}
```

---

### POST /requests/:id/accept
Accept a request (creator action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "status": "in_progress",
    "statusChangedAt": "2024-01-21T10:00:00Z"
  }
}
```

---

### POST /requests/:id/decline
Decline a request (creator action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "status": "rejected",
    "statusChangedAt": "2024-01-21T10:00:00Z"
  }
}
```

---

### POST /requests/:id/approve
Approve completed work (brand action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "status": "approved",
    "statusChangedAt": "2024-01-28T10:00:00Z"
  }
}
```

---

### POST /requests/:id/messages
Add a message to the request.

**Request:**
```json
{
  "content": "Please ensure the brand colors #3B82F6 and #10B981 are used consistently."
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "hh0e8400-e29b-41d4-a716-446655440012",
    "requestId": "dd0e8400-e29b-41d4-a716-446655440008",
    "content": "Please ensure the brand colors...",
    "sender": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "John"
    },
    "createdAt": "2024-01-20T16:00:00Z"
  }
}
```

---

### DELETE /requests/:id
Delete/cancel a request.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Request cancelled successfully"
  }
}
```

---

## 7. Projects

### GET /projects
List all projects.

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)
- `status` (optional): Filter by status
- `category` (optional): Filter by category
- `search` (optional): Search by title or creator name
- `sortBy` (optional): Sort field (createdAt, deadline, budget)
- `sortOrder` (optional): asc or desc

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "ii0e8400-e29b-41d4-a716-446655440013",
      "title": "Brand Video Campaign Q1",
      "description": "Video campaign for product launch...",
      "category": "video_campaign",
      "budget": 5000.00,
      "deadline": "2024-02-28",
      "priority": "high",
      "status": "in_progress",
      "progressPercent": 65,
      "deliverablesCount": 4,
      "completedDeliverablesCount": 2,
      "unreadMessages": 3,
      "lastActivityAt": "2024-01-20T10:00:00Z",
      "creator": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "firstName": "Sarah",
        "lastName": "Miller",
        "avatar": "https://example.com/avatars/sarah.jpg"
      }
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 8
  }
}
```

---

### POST /projects
Create a new project.

**Request:**
```json
{
  "title": "Brand Video Campaign Q1",
  "description": "Video campaign for product launch...",
  "category": "video_campaign",
  "creatorId": "550e8400-e29b-41d4-a716-446655440000",
  "budget": 5000.00,
  "deadline": "2024-02-28",
  "priority": "high",
  "deliverables": [
    {
      "name": "Hero Video",
      "description": "Main promotional video (30 seconds)",
      "dueDate": "2024-02-15"
    },
    {
      "name": "Social Cuts",
      "description": "5 variations for different platforms"
    }
  ],
  "teamMembers": [
    {
      "userId": "jj0e8400-e29b-41d4-a716-446655440014",
      "role": "manager"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "ii0e8400-e29b-41d4-a716-446655440013",
    "title": "Brand Video Campaign Q1",
    "description": "Video campaign for product launch...",
    "category": "video_campaign",
    "budget": 5000.00,
    "deadline": "2024-02-28",
    "priority": "high",
    "status": "draft",
    "progressPercent": 0,
    "createdAt": "2024-01-20T10:00:00Z",
    "deliverables": [
      {
        "id": "kk0e8400-e29b-41d4-a716-446655440015",
        "name": "Hero Video",
        "status": "pending"
      }
    ]
  }
}
```

---

### GET /projects/:id
Get a specific project with details.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "ii0e8400-e29b-41d4-a716-446655440013",
    "title": "Brand Video Campaign Q1",
    "description": "Video campaign for product launch...",
    "category": "video_campaign",
    "budget": 5000.00,
    "deadline": "2024-02-28",
    "priority": "high",
    "status": "in_progress",
    "progressPercent": 65,
    "createdAt": "2024-01-20T10:00:00Z",
    "lastActivityAt": "2024-01-25T14:00:00Z",
    "creator": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "Sarah",
      "lastName": "Miller",
      "avatar": "https://example.com/avatars/sarah.jpg"
    },
    "deliverables": [
      {
        "id": "kk0e8400-e29b-41d4-a716-446655440015",
        "name": "Hero Video",
        "description": "Main promotional video (30 seconds)",
        "dueDate": "2024-02-15",
        "status": "approved",
        "files": [
          {
            "id": "ll0e8400-e29b-41d4-a716-446655440016",
            "fileName": "hero-video-final.mp4",
            "fileSize": 25600000,
            "url": "https://storage.example.com/files/..."
          }
        ]
      }
    ],
    "teamMembers": [
      {
        "id": "jj0e8400-e29b-41d4-a716-446655440014",
        "user": {
          "firstName": "Mike",
          "lastName": "Johnson"
        },
        "role": "manager",
        "addedAt": "2024-01-20T10:00:00Z"
      }
    ]
  }
}
```

---

### PATCH /projects/:id
Update a project.

**Request:**
```json
{
  "title": "Brand Video Campaign Q1 2024",
  "deadline": "2024-03-15",
  "priority": "urgent"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "ii0e8400-e29b-41d4-a716-446655440013",
    "title": "Brand Video Campaign Q1 2024",
    "deadline": "2024-03-15",
    "priority": "urgent",
    "updatedAt": "2024-01-25T10:00:00Z"
  }
}
```

---

### POST /projects/:id/team-members
Add a team member to the project.

**Request:**
```json
{
  "userId": "mm0e8400-e29b-41d4-a716-446655440017",
  "role": "contributor"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "nn0e8400-e29b-41d4-a716-446655440018",
    "projectId": "ii0e8400-e29b-41d4-a716-446655440013",
    "user": {
      "id": "mm0e8400-e29b-41d4-a716-446655440017",
      "firstName": "Emily",
      "lastName": "Davis"
    },
    "role": "contributor",
    "addedAt": "2024-01-25T10:00:00Z"
  }
}
```

---

### DELETE /projects/:id/team-members/:memberId
Remove a team member from the project.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Team member removed from project"
  }
}
```

---

### PATCH /projects/:id/status
Update project status.

**Request:**
```json
{
  "status": "completed"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "ii0e8400-e29b-41d4-a716-446655440013",
    "status": "completed",
    "progressPercent": 100,
    "updatedAt": "2024-02-28T10:00:00Z"
  }
}
```

---

### DELETE /projects/:id
Cancel/delete a project.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Project cancelled successfully"
  }
}
```

---

## 8. Deliverables

### GET /deliverables/:id
Get a specific deliverable.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "kk0e8400-e29b-41d4-a716-446655440015",
    "projectId": "ii0e8400-e29b-41d4-a716-446655440013",
    "name": "Hero Video",
    "description": "Main promotional video (30 seconds)",
    "dueDate": "2024-02-15",
    "status": "submitted",
    "submittedAt": "2024-02-14T10:00:00Z",
    "files": [
      {
        "id": "ll0e8400-e29b-41d4-a716-446655440016",
        "fileName": "hero-video-v2.mp4",
        "fileSize": 25600000,
        "uploadedAt": "2024-02-14T10:00:00Z"
      }
    ]
  }
}
```

---

### POST /projects/:projectId/deliverables
Add a deliverable to a project.

**Request:**
```json
{
  "name": "Behind the Scenes",
  "description": "Making-of video content",
  "dueDate": "2024-02-25"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "oo0e8400-e29b-41d4-a716-446655440019",
    "projectId": "ii0e8400-e29b-41d4-a716-446655440013",
    "name": "Behind the Scenes",
    "description": "Making-of video content",
    "dueDate": "2024-02-25",
    "status": "pending",
    "createdAt": "2024-01-26T10:00:00Z"
  }
}
```

---

### PATCH /deliverables/:id
Update a deliverable.

**Request:**
```json
{
  "name": "Hero Video - Final Cut",
  "dueDate": "2024-02-20"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "kk0e8400-e29b-41d4-a716-446655440015",
    "name": "Hero Video - Final Cut",
    "dueDate": "2024-02-20",
    "updatedAt": "2024-01-26T10:00:00Z"
  }
}
```

---

### POST /deliverables/:id/submit
Submit a deliverable for review (creator action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "kk0e8400-e29b-41d4-a716-446655440015",
    "status": "submitted",
    "submittedAt": "2024-02-14T10:00:00Z"
  }
}
```

---

### POST /deliverables/:id/approve
Approve a deliverable (brand action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "kk0e8400-e29b-41d4-a716-446655440015",
    "status": "approved",
    "approvedAt": "2024-02-15T10:00:00Z"
  }
}
```

---

### POST /deliverables/:id/request-revision
Request revision on a deliverable (brand action).

**Request:**
```json
{
  "feedback": "Please adjust the color grading to be warmer."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "kk0e8400-e29b-41d4-a716-446655440015",
    "status": "revision_requested"
  }
}
```

---

### DELETE /deliverables/:id
Delete a deliverable.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Deliverable deleted successfully"
  }
}
```

---

## 9. Quotes

### GET /quotes
List all quotes (for brands or creators).

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page
- `status` (optional): Filter by status (pending, accepted, rejected, expired)

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "pp0e8400-e29b-41d4-a716-446655440020",
      "title": "Influencer Campaign Package",
      "description": "Complete influencer campaign including 3 videos and 5 posts",
      "amount": 8500.00,
      "status": "pending",
      "submittedAt": "2024-01-18T10:00:00Z",
      "expiresAt": "2024-01-25T10:00:00Z",
      "creator": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "firstName": "Marcus",
        "lastName": "Johnson",
        "avatar": "https://example.com/avatars/marcus.jpg"
      }
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 5
  }
}
```

---

### POST /quotes
Create a new quote (creator action).

**Request:**
```json
{
  "brandAccountId": "660e8400-e29b-41d4-a716-446655440001",
  "title": "Motion Graphics Package",
  "description": "5 animated explainer videos with custom illustrations",
  "amount": 6000.00,
  "expiresInDays": 7
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "qq0e8400-e29b-41d4-a716-446655440021",
    "title": "Motion Graphics Package",
    "description": "5 animated explainer videos with custom illustrations",
    "amount": 6000.00,
    "status": "pending",
    "submittedAt": "2024-01-20T10:00:00Z",
    "expiresAt": "2024-01-27T10:00:00Z"
  }
}
```

---

### GET /quotes/:id
Get a specific quote.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "pp0e8400-e29b-41d4-a716-446655440020",
    "title": "Influencer Campaign Package",
    "description": "Complete influencer campaign including 3 videos and 5 posts",
    "amount": 8500.00,
    "status": "pending",
    "submittedAt": "2024-01-18T10:00:00Z",
    "expiresAt": "2024-01-25T10:00:00Z",
    "creator": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "Marcus",
      "lastName": "Johnson",
      "avatar": "https://example.com/avatars/marcus.jpg",
      "rating": 4.8
    },
    "brand": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "companyName": "Acme Corp"
    }
  }
}
```

---

### POST /quotes/:id/accept
Accept a quote (brand action). Creates a project.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "pp0e8400-e29b-41d4-a716-446655440020",
    "status": "accepted",
    "respondedAt": "2024-01-20T10:00:00Z",
    "project": {
      "id": "rr0e8400-e29b-41d4-a716-446655440022",
      "title": "Influencer Campaign Package",
      "status": "in_progress"
    }
  }
}
```

---

### POST /quotes/:id/decline
Decline a quote (brand action).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "pp0e8400-e29b-41d4-a716-446655440020",
    "status": "rejected",
    "respondedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

## 10. Messages

### GET /conversations
List all conversations for the current user.

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page
- `search` (optional): Search by participant name

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "ss0e8400-e29b-41d4-a716-446655440023",
      "participant": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "firstName": "Alex",
        "lastName": "Kim",
        "avatar": "https://example.com/avatars/alex.jpg"
      },
      "lastMessage": {
        "content": "Looking forward to working with you!",
        "sentAt": "2024-01-20T10:00:00Z",
        "isOwn": false
      },
      "unreadCount": 1
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 5
  }
}
```

---

### POST /conversations
Start a new conversation.

**Request:**
```json
{
  "participantId": "550e8400-e29b-41d4-a716-446655440000",
  "initialMessage": "Hi! I'd love to discuss a potential project with you."
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "tt0e8400-e29b-41d4-a716-446655440024",
    "participant": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "Alex",
      "lastName": "Kim"
    },
    "createdAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### GET /conversations/:id/messages
Get messages in a conversation.

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page (default: 50)
- `before` (optional): Get messages before this timestamp

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "uu0e8400-e29b-41d4-a716-446655440025",
      "content": "Hi! Thanks for reaching out.",
      "sender": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "firstName": "Alex",
        "avatar": "https://example.com/avatars/alex.jpg"
      },
      "status": "read",
      "sentAt": "2024-01-20T09:00:00Z",
      "isOwn": false,
      "attachments": []
    },
    {
      "id": "vv0e8400-e29b-41d4-a716-446655440026",
      "content": "I'd love to hear more about your project.",
      "sender": {
        "id": "ww0e8400-e29b-41d4-a716-446655440027",
        "firstName": "You"
      },
      "status": "delivered",
      "sentAt": "2024-01-20T09:30:00Z",
      "isOwn": true,
      "attachments": []
    }
  ],
  "meta": {
    "page": 1,
    "limit": 50,
    "total": 15
  }
}
```

---

### POST /conversations/:id/messages
Send a message in a conversation.

**Request:**
```json
{
  "content": "That sounds great! When can we start?",
  "attachments": [
    {
      "fileId": "ll0e8400-e29b-41d4-a716-446655440016"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "xx0e8400-e29b-41d4-a716-446655440028",
    "conversationId": "ss0e8400-e29b-41d4-a716-446655440023",
    "content": "That sounds great! When can we start?",
    "status": "sent",
    "sentAt": "2024-01-20T11:00:00Z",
    "isOwn": true,
    "attachments": [
      {
        "id": "ll0e8400-e29b-41d4-a716-446655440016",
        "fileName": "brief.pdf",
        "fileSize": 1024000
      }
    ]
  }
}
```

---

### POST /conversations/:id/read
Mark all messages in a conversation as read.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "conversationId": "ss0e8400-e29b-41d4-a716-446655440023",
    "readAt": "2024-01-20T11:00:00Z",
    "messagesRead": 3
  }
}
```

---

### POST /conversations/:id/typing
Indicate typing status (WebSocket preferred, HTTP fallback).

**Request:**
```json
{
  "isTyping": true
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "acknowledged": true
  }
}
```

---

## 11. Favorites

### GET /favorites
Get all favorite creators.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "yy0e8400-e29b-41d4-a716-446655440029",
      "creator": {
        "id": "990e8400-e29b-41d4-a716-446655440004",
        "user": {
          "firstName": "Alex",
          "lastName": "Kim"
        },
        "specialty": "3D Art",
        "rating": 4.9,
        "avatar": "https://example.com/avatars/alex.jpg"
      },
      "addedAt": "2024-01-15T10:00:00Z"
    }
  ]
}
```

---

### POST /favorites
Add a creator to favorites.

**Request:**
```json
{
  "creatorId": "990e8400-e29b-41d4-a716-446655440004"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "zz0e8400-e29b-41d4-a716-446655440030",
    "creatorId": "990e8400-e29b-41d4-a716-446655440004",
    "addedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### DELETE /favorites/:creatorId
Remove a creator from favorites.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Creator removed from favorites"
  }
}
```

---

## 12. Reviews

### GET /creators/:creatorId/reviews
Get reviews for a creator.

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page
- `sortBy` (optional): rating, createdAt
- `sortOrder` (optional): asc, desc

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "aaa0e8400-e29b-41d4-a716-446655440031",
      "rating": 5,
      "content": "Excellent work! The 3D renders exceeded our expectations.",
      "projectType": "Product Visualization",
      "reviewer": {
        "firstName": "Sarah",
        "lastName": "M.",
        "avatar": "https://example.com/avatars/sarah.jpg",
        "company": "TechStart Inc."
      },
      "createdAt": "2024-01-10T10:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 47,
    "averageRating": 4.9
  }
}
```

---

### POST /reviews
Create a review for a completed project/request.

**Request:**
```json
{
  "creatorId": "990e8400-e29b-41d4-a716-446655440004",
  "projectId": "ii0e8400-e29b-41d4-a716-446655440013",
  "rating": 5,
  "content": "Outstanding work! Alex delivered exactly what we needed.",
  "projectType": "Video Campaign"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "bbb0e8400-e29b-41d4-a716-446655440032",
    "creatorId": "990e8400-e29b-41d4-a716-446655440004",
    "rating": 5,
    "content": "Outstanding work! Alex delivered exactly what we needed.",
    "projectType": "Video Campaign",
    "createdAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### PATCH /reviews/:id
Update your own review.

**Request:**
```json
{
  "rating": 4,
  "content": "Updated review content..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "bbb0e8400-e29b-41d4-a716-446655440032",
    "rating": 4,
    "content": "Updated review content...",
    "updatedAt": "2024-01-21T10:00:00Z"
  }
}
```

---

### DELETE /reviews/:id
Delete your own review.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Review deleted successfully"
  }
}
```

---

## 13. Portfolio

### GET /creators/:creatorId/portfolio
Get a creator's portfolio items.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "ccc0e8400-e29b-41d4-a716-446655440033",
      "title": "Abstract Flow",
      "description": "3D abstract art piece for tech brand",
      "imageUrl": "https://example.com/portfolio/1.jpg",
      "externalUrl": "https://behance.net/project/123",
      "isFeatured": true,
      "displayOrder": 1
    }
  ]
}
```

---

### POST /creators/me/portfolio
Add a portfolio item (creator action).

**Request:**
```json
{
  "title": "Brand Identity Design",
  "description": "Complete brand identity package for startup",
  "imageUrl": "https://example.com/portfolio/new.jpg",
  "externalUrl": "https://dribbble.com/shots/123",
  "isFeatured": false
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "ddd0e8400-e29b-41d4-a716-446655440034",
    "title": "Brand Identity Design",
    "description": "Complete brand identity package for startup",
    "imageUrl": "https://example.com/portfolio/new.jpg",
    "displayOrder": 7,
    "createdAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### PATCH /creators/me/portfolio/:id
Update a portfolio item.

**Request:**
```json
{
  "title": "Updated Title",
  "isFeatured": true
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "ccc0e8400-e29b-41d4-a716-446655440033",
    "title": "Updated Title",
    "isFeatured": true,
    "updatedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### PUT /creators/me/portfolio/reorder
Reorder portfolio items.

**Request:**
```json
{
  "itemIds": [
    "ddd0e8400-e29b-41d4-a716-446655440034",
    "ccc0e8400-e29b-41d4-a716-446655440033"
  ]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Portfolio reordered successfully"
  }
}
```

---

### DELETE /creators/me/portfolio/:id
Delete a portfolio item.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Portfolio item deleted"
  }
}
```

---

## 14. Files

### POST /files/upload
Upload a file. Returns a presigned URL for direct upload to storage.

**Request:**
```json
{
  "fileName": "deliverable-v1.mp4",
  "fileType": "video",
  "mimeType": "video/mp4",
  "fileSize": 25600000,
  "context": "deliverable",
  "deliverableId": "kk0e8400-e29b-41d4-a716-446655440015"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "eee0e8400-e29b-41d4-a716-446655440035",
    "uploadUrl": "https://storage.example.com/upload?signature=...",
    "uploadMethod": "PUT",
    "uploadHeaders": {
      "Content-Type": "video/mp4"
    },
    "expiresAt": "2024-01-20T11:00:00Z"
  }
}
```

---

### POST /files/:id/confirm
Confirm that a file upload is complete.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "eee0e8400-e29b-41d4-a716-446655440035",
    "fileName": "deliverable-v1.mp4",
    "fileSize": 25600000,
    "url": "https://cdn.example.com/files/deliverable-v1.mp4",
    "thumbnailUrl": "https://cdn.example.com/thumbs/deliverable-v1.jpg"
  }
}
```

---

### GET /files/:id
Get file metadata.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "eee0e8400-e29b-41d4-a716-446655440035",
    "fileName": "deliverable-v1.mp4",
    "fileType": "video",
    "mimeType": "video/mp4",
    "fileSize": 25600000,
    "url": "https://cdn.example.com/files/deliverable-v1.mp4",
    "thumbnailUrl": "https://cdn.example.com/thumbs/deliverable-v1.jpg",
    "uploadedBy": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "firstName": "Sarah"
    },
    "createdAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### DELETE /files/:id
Delete a file.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "File deleted successfully"
  }
}
```

---

## 15. Notifications

### GET /notifications
Get user notifications.

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page
- `unreadOnly` (optional): true/false

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "fff0e8400-e29b-41d4-a716-446655440036",
      "type": "status_change",
      "subject": "Project Updated",
      "body": "Your project 'Brand Video Campaign' status changed to Approved",
      "isRead": false,
      "cta": "/projects/ii0e8400-e29b-41d4-a716-446655440013",
      "createdAt": "2024-01-20T10:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 15,
    "unreadCount": 3
  }
}
```

---

### POST /notifications/:id/read
Mark a notification as read.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "fff0e8400-e29b-41d4-a716-446655440036",
    "isRead": true,
    "readAt": "2024-01-20T11:00:00Z"
  }
}
```

---

### POST /notifications/read-all
Mark all notifications as read.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "All notifications marked as read",
    "count": 3
  }
}
```

---

### DELETE /notifications/:id
Delete a notification.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Notification deleted"
  }
}
```

---

### GET /notifications/preferences
Get notification preferences.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "inAppEnabled": true,
    "emailDigestEnabled": true,
    "emailDigestFrequency": "daily",
    "soundEnabled": true,
    "browserNotificationsEnabled": true,
    "notifyMessages": true,
    "notifyStatusChanges": true,
    "notifyAssignments": true,
    "notifySystem": true
  }
}
```

---

### PATCH /notifications/preferences
Update notification preferences.

**Request:**
```json
{
  "soundEnabled": false,
  "emailDigestEnabled": true,
  "emailDigestFrequency": "weekly"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "soundEnabled": false,
    "emailDigestEnabled": true,
    "emailDigestFrequency": "weekly",
    "updatedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

## 16. Billing

### GET /billing/current-plan
Get the current subscription plan.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "plan": "pro",
    "status": "active",
    "currentPeriodStart": "2024-01-01T00:00:00Z",
    "currentPeriodEnd": "2024-02-01T00:00:00Z",
    "cancelAtPeriodEnd": false,
    "features": {
      "maxRequests": 100,
      "maxTeamMembers": 10,
      "prioritySupport": true
    }
  }
}
```

---

### POST /billing/upgrade
Upgrade subscription plan.

**Request:**
```json
{
  "plan": "enterprise"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "checkoutUrl": "https://checkout.stripe.com/session/...",
    "sessionId": "cs_test_..."
  }
}
```

---

### POST /billing/cancel
Cancel subscription at end of billing period.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Subscription will be cancelled at end of billing period",
    "cancelAt": "2024-02-01T00:00:00Z"
  }
}
```

---

### GET /billing/payment-methods
Get saved payment methods.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "ggg0e8400-e29b-41d4-a716-446655440037",
      "cardBrand": "visa",
      "cardLastFour": "4242",
      "expiryMonth": 12,
      "expiryYear": 2025,
      "isDefault": true
    }
  ]
}
```

---

### POST /billing/payment-methods
Add a new payment method.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "setupUrl": "https://checkout.stripe.com/setup/...",
    "sessionId": "seti_..."
  }
}
```

---

### DELETE /billing/payment-methods/:id
Remove a payment method.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Payment method removed"
  }
}
```

---

### GET /billing/history
Get billing history.

**Query Parameters:**
- `page` (optional): Page number
- `limit` (optional): Items per page

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "hhh0e8400-e29b-41d4-a716-446655440038",
      "amount": 49.00,
      "currency": "usd",
      "description": "Pro Plan - Monthly",
      "status": "paid",
      "paidAt": "2024-01-01T00:00:00Z",
      "invoiceUrl": "https://pay.stripe.com/invoice/..."
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 12
  }
}
```

---

### GET /creators/me/earnings
Get creator earnings (creator-only).

**Query Parameters:**
- `period` (optional): week, month, year, all

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "currentBalance": 2500.00,
    "pendingEarnings": 650.00,
    "totalEarnings": 15000.00,
    "periodEarnings": 1200.00,
    "earningsByMonth": [
      { "month": "2024-01", "amount": 1200.00 },
      { "month": "2023-12", "amount": 950.00 }
    ]
  }
}
```

---

### POST /creators/me/payouts
Request a payout (creator-only).

**Request:**
```json
{
  "amount": 1000.00
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "iii0e8400-e29b-41d4-a716-446655440039",
    "amount": 1000.00,
    "status": "pending",
    "estimatedArrival": "2024-01-25T00:00:00Z"
  }
}
```

---

## 17. Admin

*Admin endpoints require `superadmin` role.*

### GET /admin/requests
List all requests (admin view).

**Query Parameters:**
- All standard query params plus:
- `buyerId` (optional): Filter by buyer
- `creatorId` (optional): Filter by creator

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "dd0e8400-e29b-41d4-a716-446655440008",
      "contentType": "image",
      "budget": 250.00,
      "status": "submitted",
      "buyer": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "buyer@example.com"
      },
      "creator": {
        "id": "ee0e8400-e29b-41d4-a716-446655440009",
        "email": "creator@example.com"
      },
      "createdAt": "2024-01-20T10:00:00Z"
    }
  ]
}
```

---

### POST /admin/requests/:id/assign
Assign a creator to a request.

**Request:**
```json
{
  "creatorId": "ee0e8400-e29b-41d4-a716-446655440009"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "dd0e8400-e29b-41d4-a716-446655440008",
    "assignedCreator": {
      "id": "ee0e8400-e29b-41d4-a716-446655440009",
      "firstName": "Maria",
      "lastName": "Santos"
    }
  }
}
```

---

### GET /admin/creators
List all creators with admin details.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "user": {
        "id": "ee0e8400-e29b-41d4-a716-446655440009",
        "email": "maria@creative.co",
        "firstName": "Maria",
        "lastName": "Santos"
      },
      "rating": 4.9,
      "isAvailable": true,
      "balance": 2500.00,
      "projectsCompleted": 45
    }
  ]
}
```

---

### PATCH /admin/creators/:id
Update creator profile (admin).

**Request:**
```json
{
  "isAvailable": false,
  "balance": 3000.00
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "isAvailable": false,
    "balance": 3000.00,
    "updatedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### GET /admin/brands
List all brands with admin details.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "cc0e8400-e29b-41d4-a716-446655440007",
      "companyName": "Acme Corp",
      "companyEmail": "contact@acme.com",
      "subscriptionPlan": "enterprise",
      "totalRequests": 45,
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

---

### PATCH /admin/brands/:id
Update brand profile (admin).

**Request:**
```json
{
  "subscriptionPlan": "enterprise"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "cc0e8400-e29b-41d4-a716-446655440007",
    "subscriptionPlan": "enterprise",
    "updatedAt": "2024-01-20T10:00:00Z"
  }
}
```

---

### GET /admin/stats
Get platform statistics.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "totalUsers": 1250,
    "totalCreators": 450,
    "totalBrands": 320,
    "totalRequests": 2500,
    "totalProjects": 890,
    "activeProjects": 145,
    "monthlyRevenue": 45000.00,
    "pendingPayouts": 12500.00
  }
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Request validation failed |
| `UNAUTHORIZED` | Authentication required |
| `FORBIDDEN` | Insufficient permissions |
| `NOT_FOUND` | Resource not found |
| `CONFLICT` | Resource already exists |
| `RATE_LIMITED` | Too many requests |
| `INTERNAL_ERROR` | Internal server error |

---

## Rate Limits

| Endpoint Type | Limit |
|---------------|-------|
| Authentication | 10 requests/minute |
| Standard API | 100 requests/minute |
| File Upload | 20 requests/minute |
| Admin | 50 requests/minute |

---

## WebSocket Events

For real-time features (messaging, notifications), connect to:
```
wss://api.pixelperfect.app/v1/ws
```

### Events:

**Incoming:**
- `message.new` - New message received
- `message.status` - Message status updated
- `notification.new` - New notification
- `typing.start` - User started typing
- `typing.stop` - User stopped typing

**Outgoing:**
- `message.send` - Send a message
- `typing.update` - Update typing status
- `conversation.read` - Mark conversation as read
