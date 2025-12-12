# WSR Email CLI - Implementation Specification

**Version:** 1.0
**Status:** Draft
**Author:** Claude Code
**Date:** 2025-12-11

## Overview

A .NET CLI tool that renders rich HTML emails from JSON input and sends them via SMTP. Designed to be called from Python scripts (or any language) via subprocess, providing enterprise-grade email rendering with full Outlook/Gmail compatibility.

## Goals

1. **Outlook-compatible HTML** - Table-based layouts, inline CSS, MSO conditionals
2. **Language-agnostic** - JSON in, JSON out, callable from any language
3. **Reusable** - Not WSR-specific; can render any template with any data
4. **Standalone** - Single executable, no external dependencies at runtime
5. **Testable** - Render-only mode for previewing without sending

---

## CLI Interface

### Command: `render`

Render a template to HTML without sending.

```bash
wsr-email-cli render \
  --template <template-name> \
  --data <json-file-or-stdin> \
  --output <html-file-or-stdout>
```

**Examples:**
```bash
# Render to file
wsr-email-cli render --template wsr-report --data report.json --output preview.html

# Render to stdout (for piping)
cat report.json | wsr-email-cli render --template wsr-report --output -

# Render with inline JSON
wsr-email-cli render --template wsr-report --data '{"title":"Weekly Report"}' --output -
```

### Command: `send`

Render and send an email.

```bash
wsr-email-cli send \
  --template <template-name> \
  --data <json-file-or-stdin> \
  --to <email-addresses> \
  --subject <subject-line> \
  [--cc <cc-addresses>] \
  [--from <from-address>] \
  [--config <config-file>] \
  [--dry-run]
```

**Examples:**
```bash
# Send email
wsr-email-cli send \
  --template wsr-report \
  --data report.json \
  --to "manager@company.com,team@company.com" \
  --subject "Weekly Status Report - Dec 5-11, 2025"

# Dry run (render but don't send, output what would be sent)
wsr-email-cli send \
  --template wsr-report \
  --data report.json \
  --to "test@example.com" \
  --subject "Test" \
  --dry-run

# With config file
wsr-email-cli send \
  --template wsr-report \
  --data report.json \
  --config ~/.wsr-email/config.json \
  --to "manager@company.com"
```

### Command: `list-templates`

List available templates.

```bash
wsr-email-cli list-templates [--format json|table]
```

### Command: `validate`

Validate JSON data against a template's expected schema.

```bash
wsr-email-cli validate --template wsr-report --data report.json
```

### Command: `config`

Manage SMTP configuration.

```bash
# Initialize config interactively
wsr-email-cli config init

# Show current config (redacted passwords)
wsr-email-cli config show

# Test SMTP connection
wsr-email-cli config test
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Template not found |
| 4 | Data validation failed |
| 5 | SMTP connection failed |
| 6 | Send failed |
| 7 | Configuration error |

---

## JSON Input Schema

### Common Envelope

All templates receive data wrapped in a standard envelope:

```json
{
  "template": "wsr-report",
  "language": "en",
  "branding": {
    "companyName": "Valco Industries Inc.",
    "productName": "XTConnect",
    "logoBase64": "data:image/png;base64,...",
    "primaryColor": "#007bff",
    "accentColor": "#28a745",
    "supportEmail": "support@company.com",
    "supportPhone": "(888) 555-1234",
    "websiteUrl": "https://company.com",
    "copyrightYear": 2025
  },
  "data": {
    // Template-specific data (see below)
  }
}
```

### WSR Report Template Data

Template name: `wsr-report`

```json
{
  "template": "wsr-report",
  "language": "en",
  "branding": { ... },
  "data": {
    "reportTitle": "Weekly Status Report",
    "dateRange": "December 5-11, 2025",
    "weekId": "2025-W50",
    "author": {
      "name": "Sean Developer",
      "email": "sean@company.com",
      "team": "Platform Engineering"
    },
    "summary": {
      "completed": 5,
      "inProgress": 3,
      "blocked": 1,
      "onHold": 0,
      "totalWorkItems": 12,
      "totalCommits": 23,
      "linesAdded": 1456,
      "linesRemoved": 342
    },
    "highlights": [
      "Completed authentication service refactor",
      "Deployed v2.3.1 to production",
      "Resolved critical bug in payment processing"
    ],
    "entries": [
      {
        "index": 1,
        "title": "Authentication Service Refactor",
        "status": "Completed",
        "priority": "High",
        "domain": "Security",
        "timeline": "December 5-9, 2025",
        "objective": "Modernize authentication to support OAuth 2.0 and improve security posture.",
        "solution": "Implemented PKCE flow, added refresh token rotation, migrated to JWT with short expiry.",
        "businessImpact": "Enables SSO integration with enterprise customers, reducing onboarding friction.",
        "technicalImpact": "Reduced auth latency by 40%, improved token security.",
        "nextSteps": "Monitor production metrics, begin SSO integration with first enterprise client.",
        "codeStats": {
          "filesChanged": 15,
          "insertions": 1234,
          "deletions": 456
        },
        "workItems": [
          {
            "id": 1234,
            "type": "User Story",
            "title": "Implement OAuth 2.0 PKCE Flow",
            "url": "https://dev.azure.com/org/project/_workitems/edit/1234"
          },
          {
            "id": 1235,
            "type": "Task",
            "title": "Add refresh token rotation",
            "url": "https://dev.azure.com/org/project/_workitems/edit/1235"
          }
        ],
        "commits": [
          {
            "sha": "abc1234def5678",
            "shortSha": "abc1234",
            "subject": "feat: implement PKCE authorization flow",
            "url": "https://dev.azure.com/org/project/_git/repo/commit/abc1234def5678"
          }
        ]
      }
    ],
    "blockers": [
      {
        "title": "Waiting on security review approval",
        "dependency": "InfoSec Team",
        "impact": "Delays production deployment by 2 days",
        "workItemId": 1240,
        "workItemUrl": "https://dev.azure.com/org/project/_workitems/edit/1240"
      }
    ],
    "upcomingWork": [
      "Begin API rate limiting implementation",
      "Start database migration planning",
      "Complete documentation updates"
    ],
    "notes": "Team velocity is tracking 10% above sprint average. Holiday schedules may impact next week's capacity."
  }
}
```

### Generic Template Data

Template name: `generic`

For simple notifications without complex structure:

```json
{
  "template": "generic",
  "language": "en",
  "branding": { ... },
  "data": {
    "title": "Notification Title",
    "preheader": "Brief preview text for email clients",
    "greeting": "Hello Team,",
    "sections": [
      {
        "heading": "Section Title",
        "content": "Paragraph content here. Can include **markdown**.",
        "type": "text"
      },
      {
        "heading": "Key Metrics",
        "type": "kpi",
        "items": [
          { "label": "Total", "value": "42", "color": "primary" },
          { "label": "Success", "value": "95%", "color": "success" }
        ]
      },
      {
        "heading": "Action Items",
        "type": "list",
        "items": ["Item one", "Item two", "Item three"]
      },
      {
        "type": "button",
        "text": "View Dashboard",
        "url": "https://dashboard.company.com"
      }
    ],
    "closing": "Best regards,\nThe Platform Team",
    "footerLinks": [
      { "text": "Unsubscribe", "url": "https://..." },
      { "text": "Preferences", "url": "https://..." }
    ]
  }
}
```

---

## JSON Output Schema

### Success Response

```json
{
  "success": true,
  "messageId": "550e8400-e29b-41d4-a716-446655440000",
  "sentAt": "2025-12-11T14:30:00Z",
  "recipients": {
    "to": ["manager@company.com", "team@company.com"],
    "cc": ["director@company.com"]
  },
  "subject": "Weekly Status Report - December 5-11, 2025",
  "htmlLength": 45678,
  "plainTextLength": 2345,
  "embeddedImages": 1
}
```

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "SMTP_CONNECTION_FAILED",
    "message": "Unable to connect to SMTP server",
    "details": "Connection timed out after 30000ms",
    "retryable": true
  }
}
```

### Render-Only Response

```json
{
  "success": true,
  "html": "<!DOCTYPE html>...",
  "plainText": "Weekly Status Report...",
  "subject": "Weekly Status Report - December 5-11, 2025",
  "embeddedImages": [
    {
      "contentId": "logo",
      "mimeType": "image/png",
      "base64Length": 12345
    }
  ]
}
```

---

## Configuration File

Location: `~/.wsr-email/config.json` or specified via `--config`

```json
{
  "smtp": {
    "server": "smtp.office365.com",
    "port": 587,
    "useTls": true,
    "username": "noreply@company.com",
    "passwordEnvVar": "WSR_EMAIL_PASSWORD",
    "timeoutMs": 30000,
    "maxRetries": 3,
    "retryDelayMs": 1000
  },
  "defaults": {
    "fromAddress": "noreply@company.com",
    "fromName": "Status Reports",
    "replyTo": "team@company.com"
  },
  "branding": {
    "companyName": "Valco Industries Inc.",
    "productName": "XTConnect",
    "logoPath": "~/.wsr-email/logo.png",
    "primaryColor": "#007bff",
    "accentColor": "#28a745",
    "supportEmail": "support@company.com",
    "websiteUrl": "https://company.com"
  },
  "templates": {
    "searchPaths": [
      "~/.wsr-email/templates",
      "/usr/local/share/wsr-email/templates"
    ],
    "cacheMinutes": 30
  }
}
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `WSR_EMAIL_PASSWORD` | SMTP password (never stored in config file) |
| `WSR_EMAIL_CONFIG` | Override default config file location |
| `WSR_EMAIL_TEMPLATES` | Additional template search path |

---

## Template System

### Template Location

Templates are Razor `.cshtml` files located in:
1. Config-specified paths (`templates.searchPaths`)
2. Built-in templates (embedded in executable)

### Built-in Templates

| Name | Purpose |
|------|---------|
| `wsr-report` | Weekly status report with KPIs, entries, blockers |
| `wsr-executive` | Executive summary (abbreviated) |
| `generic` | Flexible notification template |
| `alert` | Critical alert with prominent styling |

### Template Structure

```
templates/
├── _Layout.cshtml              # Shared base layout
├── _Partials/
│   ├── _Header.cshtml          # Email header with logo
│   ├── _Footer.cshtml          # Footer with links
│   ├── _KpiCard.cshtml         # KPI metric card
│   ├── _StatusBadge.cshtml     # Status indicator badge
│   └── _WorkItemLink.cshtml    # Work item hyperlink
├── wsr-report.cshtml           # WSR full report
├── wsr-executive.cshtml        # WSR executive summary
├── generic.cshtml              # Generic notification
└── alert.cshtml                # Critical alert
```

### Template Requirements

All templates MUST:

1. **Use table-based layout** (no flexbox/grid)
2. **Inline all CSS** or use `<style>` in `<head>` only
3. **Include MSO conditionals** for Outlook
4. **Support dark mode** via `prefers-color-scheme` meta
5. **Generate plain text alternative** (via `@section PlainText`)
6. **Use CID references for images** (`src="cid:logo"`)

### Base Layout Features

The `_Layout.cshtml` provides:

```html
<!DOCTYPE html>
<html lang="@Model.Language" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="x-apple-disable-message-reformatting">
    <meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>@Model.Data.ReportTitle</title>

    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
                <o:AllowPNG/>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <style type="text/css">
        table { border-collapse: collapse !important; }
        .mso-hide { display: none !important; }
    </style>
    <![endif]-->

    <style type="text/css">
        /* Reset styles */
        body, table, td { margin: 0; padding: 0; }
        img { border: 0; display: block; }

        /* Base styles */
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.5;
            color: #212529;
            background-color: #f4f4f4;
        }

        /* Dark mode support */
        @media (prefers-color-scheme: dark) {
            body { background-color: #1a1a1a !important; }
            .email-body { background-color: #2d2d2d !important; }
            .text-primary { color: #ffffff !important; }
        }
    </style>
</head>
<body>
    @RenderBody()
</body>
</html>
```

---

## Embedded Images

### Logo Embedding

The CLI embeds images as linked resources with Content-ID:

```csharp
var logoPath = config.Branding.LogoPath;
var logoBytes = File.ReadAllBytes(logoPath);
var linkedResource = new LinkedResource(new MemoryStream(logoBytes), "image/png")
{
    ContentId = "logo",
    TransferEncoding = TransferEncoding.Base64
};
htmlView.LinkedResources.Add(linkedResource);
```

### Template Usage

```html
<img src="cid:logo" alt="@Model.Branding.CompanyName" width="150" height="50"
     style="display:block; max-width:150px; height:auto;">
```

### Custom Images

Data can include additional images:

```json
{
  "data": {
    "images": [
      {
        "contentId": "chart1",
        "base64": "data:image/png;base64,iVBORw0KGgo...",
        "alt": "Velocity Chart"
      }
    ]
  }
}
```

---

## Error Handling

### SMTP Errors

| Error Code | Meaning | Retryable |
|------------|---------|-----------|
| `SMTP_CONNECTION_FAILED` | Cannot connect to server | Yes |
| `SMTP_AUTH_FAILED` | Invalid credentials | No |
| `SMTP_TIMEOUT` | Operation timed out | Yes |
| `SMTP_REJECTED` | Server rejected message | No |
| `SMTP_QUOTA_EXCEEDED` | Sending limit reached | Yes (with delay) |

### Template Errors

| Error Code | Meaning |
|------------|---------|
| `TEMPLATE_NOT_FOUND` | Template name doesn't exist |
| `TEMPLATE_COMPILE_ERROR` | Razor syntax error |
| `TEMPLATE_RENDER_ERROR` | Runtime error during render |

### Data Errors

| Error Code | Meaning |
|------------|---------|
| `DATA_INVALID_JSON` | Malformed JSON input |
| `DATA_MISSING_REQUIRED` | Required field missing |
| `DATA_TYPE_MISMATCH` | Field has wrong type |

---

## Logging

### Log Levels

Controlled via `--verbosity` flag:

| Level | Output |
|-------|--------|
| `quiet` | Errors only |
| `normal` | Errors + result summary |
| `verbose` | + Template rendering details |
| `debug` | + SMTP conversation, full data |

### Log Output

Logs go to stderr, result JSON to stdout:

```bash
# Normal usage - JSON to stdout, logs to stderr
wsr-email-cli send --template wsr-report --data report.json --to user@example.com > result.json

# Verbose logging
wsr-email-cli send --template wsr-report --data report.json --to user@example.com --verbosity verbose
```

---

## Python Integration

### Example: `wsr_notify.py` Integration

```python
import subprocess
import json
from pathlib import Path

def send_via_cli(template: str, data: dict, to: list[str], subject: str) -> dict:
    """Send email via wsr-email-cli."""

    # Prepare input
    input_json = json.dumps(data)

    # Build command
    cmd = [
        "wsr-email-cli", "send",
        "--template", template,
        "--data", "-",  # Read from stdin
        "--to", ",".join(to),
        "--subject", subject
    ]

    # Execute
    result = subprocess.run(
        cmd,
        input=input_json,
        capture_output=True,
        text=True,
        timeout=60
    )

    # Parse result
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        error = json.loads(result.stdout) if result.stdout else {
            "success": False,
            "error": {"code": "CLI_ERROR", "message": result.stderr}
        }
        return error


def render_preview(template: str, data: dict) -> str:
    """Render email to HTML for preview."""

    cmd = [
        "wsr-email-cli", "render",
        "--template", template,
        "--data", "-",
        "--output", "-"
    ]

    result = subprocess.run(
        cmd,
        input=json.dumps(data),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        response = json.loads(result.stdout)
        return response.get("html", "")
    else:
        raise RuntimeError(f"Render failed: {result.stderr}")
```

### Data Transformation

The Python side transforms `WeeklyData` to CLI format:

```python
def weekly_data_to_cli_format(data: WeeklyData, config: WSRConfig) -> dict:
    """Transform WeeklyData to CLI input format."""

    return {
        "template": "wsr-report",
        "language": "en",
        "branding": {
            "companyName": config.company_name or "Company",
            "logoPath": config.logo_path,
            "primaryColor": "#007bff",
            "supportEmail": config.support_email
        },
        "data": {
            "reportTitle": "Weekly Status Report",
            "dateRange": format_date_range(data.period_start, data.period_end),
            "weekId": data.week_id,
            "summary": {
                "completed": sum(1 for e in data.entries if e.get("status") == "Completed"),
                "inProgress": sum(1 for e in data.entries if e.get("status") == "In Progress"),
                "blocked": sum(1 for e in data.entries if e.get("status") == "Blocked"),
                # ... etc
            },
            "entries": [transform_entry(e, config) for e in data.entries],
            # ... etc
        }
    }
```

---

## Installation & Distribution

### Distribution Format

Single self-contained executable:

```bash
# Linux
wsr-email-cli-linux-x64

# macOS (Intel)
wsr-email-cli-osx-x64

# macOS (Apple Silicon)
wsr-email-cli-osx-arm64

# Windows
wsr-email-cli-win-x64.exe
```

### Installation Locations

| OS | Recommended Path |
|----|------------------|
| Linux | `/usr/local/bin/wsr-email-cli` |
| macOS | `/usr/local/bin/wsr-email-cli` |
| Windows | `C:\Tools\wsr-email-cli.exe` |

### First Run

```bash
# Initialize configuration
wsr-email-cli config init

# Test connection
wsr-email-cli config test

# Send test email
wsr-email-cli send \
  --template generic \
  --data '{"data":{"title":"Test","greeting":"Hello","sections":[]}}' \
  --to "your@email.com" \
  --subject "WSR Email CLI Test"
```

---

## Project Structure

```
wsr-email-cli/
├── src/
│   ├── WsrEmailCli/
│   │   ├── Program.cs                 # Entry point, CLI parsing
│   │   ├── Commands/
│   │   │   ├── RenderCommand.cs       # render command
│   │   │   ├── SendCommand.cs         # send command
│   │   │   ├── ConfigCommand.cs       # config command
│   │   │   └── ValidateCommand.cs     # validate command
│   │   ├── Services/
│   │   │   ├── IEmailRenderer.cs      # Rendering interface
│   │   │   ├── RazorEmailRenderer.cs  # RazorLight implementation
│   │   │   ├── IEmailSender.cs        # Sending interface
│   │   │   ├── SmtpEmailSender.cs     # SMTP implementation
│   │   │   └── PlainTextGenerator.cs  # HTML to plain text
│   │   ├── Models/
│   │   │   ├── EmailEnvelope.cs       # Input envelope
│   │   │   ├── SendResult.cs          # Output result
│   │   │   ├── CliConfig.cs           # Configuration model
│   │   │   └── BrandingConfig.cs      # Branding settings
│   │   ├── Templates/                 # Embedded templates
│   │   │   ├── _Layout.cshtml
│   │   │   ├── _Partials/
│   │   │   ├── wsr-report.cshtml
│   │   │   ├── wsr-executive.cshtml
│   │   │   └── generic.cshtml
│   │   └── Resources/
│   │       └── default-logo.png       # Fallback logo
│   └── WsrEmailCli.Tests/
│       ├── RenderTests.cs
│       ├── SendTests.cs
│       └── TemplateTests.cs
├── templates/                          # Additional templates (not embedded)
├── docs/
│   ├── USAGE.md
│   └── TEMPLATES.md
├── WsrEmailCli.sln
└── README.md
```

---

## Dependencies

### NuGet Packages

```xml
<PackageReference Include="System.CommandLine" Version="2.0.0-beta4" />
<PackageReference Include="RazorLight" Version="2.3.1" />
<PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
<PackageReference Include="MailKit" Version="4.3.0" />
<PackageReference Include="Microsoft.Extensions.Logging" Version="8.0.0" />
<PackageReference Include="Microsoft.Extensions.Configuration" Version="8.0.0" />
```

### Runtime Requirements

- .NET 8 Runtime (or self-contained build)
- Network access to SMTP server

---

## Security Considerations

1. **Password Storage**: Never in config file, always via environment variable
2. **TLS Required**: Enforce TLS for SMTP connections
3. **Input Validation**: Sanitize all input data before rendering
4. **No Command Injection**: Data passed via stdin, not command arguments
5. **Template Security**: Templates compiled, not evaluated as arbitrary code

---

## Future Enhancements

### Phase 2

- [ ] HTML to PDF conversion (WeasyPrint integration)
- [ ] Template hot-reload in development mode
- [ ] DKIM signing support
- [ ] Email tracking pixels (optional)
- [ ] Batch sending mode

### Phase 3

- [ ] Graph API support (Microsoft 365)
- [ ] AWS SES support
- [ ] SendGrid support
- [ ] Template versioning
- [ ] A/B testing support

---

## Acceptance Criteria

### MVP Requirements

1. ✅ `render` command produces valid HTML
2. ✅ `send` command delivers email via SMTP
3. ✅ HTML renders correctly in Outlook 365
4. ✅ HTML renders correctly in Gmail
5. ✅ HTML renders correctly in Apple Mail
6. ✅ Plain text alternative is readable
7. ✅ Logo image displays (CID embedding)
8. ✅ JSON input/output works with Python subprocess
9. ✅ Configuration file is loaded correctly
10. ✅ Password is read from environment variable
11. ✅ Exit codes are correct for all error conditions
12. ✅ Self-contained executable runs without .NET installed

---

## Testing Plan

### Unit Tests

- Template rendering with mock data
- JSON parsing and validation
- Plain text generation
- Configuration loading

### Integration Tests

- SMTP connection to test server
- Full send/receive cycle
- Various email clients (Outlook, Gmail, Apple Mail)

### Manual Testing

- Visual inspection in Litmus or Email on Acid
- Dark mode rendering
- Mobile responsive design

---

## Appendix A: Sample WSR Report Output

See `/Users/sean/source/tools/claude-tools/skills/wsr-generator/specs/SAMPLE_EMAIL.html` for rendered example.

## Appendix B: Email Client Compatibility Matrix

| Client | Tables | Inline CSS | MSO | CID Images | Dark Mode |
|--------|--------|------------|-----|------------|-----------|
| Outlook 365 | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Outlook 2019 | ✅ | ✅ | ✅ | ✅ | ❌ |
| Gmail | ✅ | ✅ | N/A | ✅ | ✅ |
| Apple Mail | ✅ | ✅ | N/A | ✅ | ✅ |
| iOS Mail | ✅ | ✅ | N/A | ✅ | ✅ |
| Thunderbird | ✅ | ✅ | N/A | ✅ | ✅ |

---

*End of Specification*
