# ScholarSync V2

A ground-up rewrite of [ScholarSync](https://github.com/Drainsoul/ScholarSync), the City of Taguig scholarship
platform. Students build a profile, check which programs they qualify for, apply with their documents and track their
allowances. Program staff review applications, manage scholars and terms and run disbursements. The scholarship office
oversees every program, staff account and report.

**Status:** planning. No application code yet; see the roadmap in the spec.

## Stack
Django 5.2 LTS (Python 3.13, uv) · PostgreSQL (Neon) · Django templates + HTMX + a little TypeScript (Vite) ·
Cloudflare R2 for files · Resend for email · deployed on Vercel.

## Docs
- [Design spec and roadmap](docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md): architecture, domain model,
  security, deployment, milestones.
- [Legacy audit](docs/legacy-audit.md): what v1 does, its business rules and its problems; the feature-parity
  checklist.
- [CLAUDE.md](CLAUDE.md): project structure, commands and conventions.

## License
[MIT](LICENSE)
