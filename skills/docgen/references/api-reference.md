# API Documentation Template

## Required Context

Before writing, gather:
1. Output from `find_endpoints.py`
2. Controller source files
3. DTO/Model class definitions
4. Authentication configuration

## Document Structure

```markdown
# API Reference

## Overview

Base URL: `https://localhost:5001/api`

### Authentication
[Requirements from analysis]

### Common Response Codes
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Validation error |
| 401 | Unauthorized |
| 404 | Not Found |

---

## [Controller Name]

Base Route: `/api/[route]`

[Controller purpose]

### [HTTP Method] [Route]

**Description**: [What it does]

**Authorization**: [Required/Optional] [Roles]

**Parameters**:
| Name | Type | Location | Required | Description |
|------|------|----------|----------|-------------|

**Request Body** (if applicable):
```json
{ "example": "value" }
```

**Response**:
| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Validation error |

**Success Response**:
```json
{ "id": 1, "name": "Example" }
```
```

## Endpoint Template

```markdown
### [METHOD] [/route/{param}]

**Description**: [Action description]

**Authorization**: [None | Required | Roles: Admin, User]

**Parameters**:
| Name | Type | Location | Required | Description |
|------|------|----------|----------|-------------|
| id | int | path | Yes | Resource identifier |
| filter | string | query | No | Filter expression |

**Request Body**:
```json
{
  "property": "value"
}
```

**Responses**:
| Status | Description |
|--------|-------------|
| 200 OK | Success |
| 400 Bad Request | Validation error |
| 404 Not Found | Resource not found |

**Example Response** (200):
```json
{
  "id": 1,
  "name": "Example",
  "createdAt": "2024-01-15T10:30:00Z"
}
```
```

## Quality Checklist

- [ ] All endpoints from scan documented
- [ ] Route patterns accurate
- [ ] Parameter types and locations correct
- [ ] Request/response examples realistic
- [ ] Status codes cover success and errors
- [ ] Authentication requirements noted
