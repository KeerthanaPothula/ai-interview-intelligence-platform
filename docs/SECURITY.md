# Security

This is a short index, not a duplicate. The authoritative, detailed security
document for this project is the root [SECURITY.md](../SECURITY.md) — it
covers authentication & session security, security headers, file upload
validation, input validation, logging/audit, and dependency-audit
instructions, with the reasoning behind each control and its known
limitations.

Use this page only to jump to the right place:

| If you want... | Go to |
|---|---|
| How login, JWT access tokens, refresh-token rotation, and account lockout work | [SECURITY.md § Authentication & Session Security](../SECURITY.md#authentication--session-security) |
| A sequence diagram of the login/refresh flow | [ARCHITECTURE.md § 3. Authentication Flow](./ARCHITECTURE.md#3-authentication-flow) |
| Which response headers are set and why | [SECURITY.md § Security Headers](../SECURITY.md#security-headers) |
| How uploaded audio/resume files are validated (MIME, size, magic bytes, malware-scan hook) | [SECURITY.md § File Upload Validation](../SECURITY.md#file-upload-validation) |
| What's logged for security events, and what is deliberately never logged | [SECURITY.md § Logging & Audit](../SECURITY.md#logging--audit) |
| How to audit Python/JS dependencies for known vulnerabilities | [SECURITY.md § Dependency Security](../SECURITY.md#dependency-security) |
| How ownership is enforced (404, not 403, on cross-user access) | [DATABASE.md § Ownership](./DATABASE.md) |
| How to report a vulnerability | Open a [private GitHub security advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) rather than a public issue |

## Related documentation

- [../SECURITY.md](../SECURITY.md) — canonical security documentation.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — authentication flow diagram.
- [DATABASE.md](./DATABASE.md) — ownership model and cascade behavior.
