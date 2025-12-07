# API Documentation Prompt

Use this prompt structure when generating API reference documentation.

## Context to Gather First

Before writing, ensure you have:
1. Output from `find_endpoints.py` (controllers, endpoints, parameters)
2. Contents of controller files (for detailed logic understanding)
3. DTO/Model classes used in requests and responses
4. Any authentication/authorization configuration

## Prompt Template

```
Based on my analysis of this ASP.NET Web API, generate API Reference documentation.

## Endpoint Analysis Results
[Paste find_endpoints.py JSON output]

## Controller Source Files
[Paste relevant controller code]

## DTO/Model Definitions
[Paste request/response model definitions]

## Requirements for the Document

1. **Overview Section**
   - Base URL and versioning (if applicable)
   - Authentication requirements
   - Common headers
   - Rate limiting (if configured)

2. **Endpoint Listing by Controller**
   For each controller:
   - Controller purpose/description
   - Base route
   
   For each endpoint:
   - HTTP method and full route
   - Description of what it does
   - Request parameters (path, query, body)
   - Request body schema (if applicable)
   - Response schema with example
   - Possible status codes
   - Authorization requirements

3. **Common Models**
   - Shared DTOs used across endpoints
   - Enum definitions
   - Error response format

4. **Error Handling**
   - Standard error response format
   - Common error codes and meanings

## Output Format
- Markdown with clear heading hierarchy
- Tables for parameters and status codes
- JSON code blocks for request/response examples
- Group endpoints logically by resource/controller
```

## Endpoint Documentation Template

### [HTTP Method] [Route]

**Description**: [Clear one-line description]

**Authorization**: [Required/Optional/None] [Roles if applicable]

**Parameters**:

| Name | Type | Location | Required | Description |
|------|------|----------|----------|-------------|
| id | int | path | Yes | The resource identifier |
| filter | string | query | No | Filter expression |

**Request Body** (if applicable):
```json
{
  "property": "value",
  "nested": {
    "child": "value"
  }
}
```

**Response**:

| Status | Description |
|--------|-------------|
| 200 OK | Success |
| 400 Bad Request | Validation error |
| 404 Not Found | Resource not found |

**Success Response** (200):
```json
{
  "id": 1,
  "name": "Example",
  "createdAt": "2024-01-15T10:30:00Z"
}
```

**Error Response** (400):
```json
{
  "type": "validation_error",
  "title": "Validation Failed",
  "errors": {
    "property": ["Error message"]
  }
}
```

---

## Example Grouping Structure

```markdown
# API Reference

## Overview

Base URL: `https://api.example.com/v1`

### Authentication

All endpoints require a Bearer token in the Authorization header:
```
Authorization: Bearer <token>
```

### Common Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - validation error |
| 401 | Unauthorized - missing or invalid token |
| 403 | Forbidden - insufficient permissions |
| 404 | Not Found |
| 500 | Internal Server Error |

---

## Controllers

### Collection Controller

Base Route: `/api/collection`

Manages data collection from hardware controllers.

#### POST /api/collection/collect/{serialNumber}

Triggers a data collection for a specific controller.

[... detailed documentation ...]

---

### Serial Port Controller

Base Route: `/api/serial`

Manages serial port connections and diagnostics.

[... detailed documentation ...]
```

## Quality Checklist

Before finalizing API documentation, verify:

- [ ] All endpoints from scan are documented
- [ ] Route patterns are accurate
- [ ] Parameter types and locations are correct
- [ ] Request/response examples are realistic
- [ ] Status codes cover success and error cases
- [ ] Authentication requirements are noted
- [ ] No placeholder text remains
