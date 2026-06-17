# Code Review Checklist

## Code Quality

- [ ] All imports follow layer rules (api_server -> infrastructure -> core)
- [ ] No forbidden naming suffixes (Manager, Handler, Helper, Utils, Processor, standalone Service)
- [ ] All public functions have type annotations
- [ ] No magic numbers or strings in business logic
- [ ] No functions exceeding 80 lines (ruff PLR0915)
- [ ] No classes exceeding 500 lines
- [ ] No copy-paste duplication introduced
- [ ] Unused imports or variables removed
- [ ] Error paths and boundary conditions handled
- [ ] Logging uses structured format (no print statements)

## Security (OWASP Top 10 Focus)

- [ ] A01 Broken Access Control: Endpoints check authentication and authorization
- [ ] A02 Cryptographic Failures: Secrets not hardcoded; sensitive data encrypted
- [ ] A03 Injection: Parameterized queries only; no raw string interpolation in SQL
- [ ] A04 Insecure Design: Input validation at API boundaries
- [ ] A05 Security Misconfiguration: No debug mode in production config
- [ ] A06 Vulnerable Components: New dependencies checked for known CVEs
- [ ] A07 Auth Failures: JWT validation present on protected routes
- [ ] A08 Data Integrity: Serialization uses safe libraries (no pickle for user data)
- [ ] A09 Logging Failures: No sensitive data in log output
- [ ] A10 SSRF: External URLs validated before requests

## Spec Compliance

- [ ] Clean Architecture layer boundaries respected
- [ ] API endpoints match spec (method, path, request/response schema)
- [ ] DB model changes match data model spec
- [ ] Domain events match event catalog
- [ ] Naming conventions followed (see docs/guides/naming-conventions.md)
- [ ] Error codes match error code spec
- [ ] Pydantic models used for configuration (not plain classes)
