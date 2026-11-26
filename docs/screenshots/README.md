# Screenshots

A tour of ScholarSync, one walkthrough per role. Every screen comes from a local explore-mode copy
(`docker compose up`) loaded with the demo data, so all people, schools and amounts are fictional.

| Who | What they do | Walkthrough |
|---|---|---|
| Visitor | Reads about the programs, signs up or logs in | [Public pages](public/README.md) |
| Student | Builds a profile, finds and applies to programs, tracks allowances and renews | [Student](student/README.md) |
| Program staff | Reviews applications, manages scholars, prepares payouts, answers students | [Program staff](program-staff/README.md) |
| Program head | Everything staff do, plus approving payouts and reports, program settings and the audit log | [Program head](program-head/README.md) |
| Scholarship office | Runs every program: programs, accounts, schools, terms, reports, analytics and support | [Scholarship office](office/README.md) |

## Try it yourself

Run `docker compose up`, open <http://127.0.0.1:8000>, and pick an account under
**Exploring ScholarSync? Use a test account** on the login page. The test accounts share the password
`explore-demo-2026`, which the login page also shows.

| Account | Email | Shown in |
|---|---|---|
| New student (Bea Navarro) | `new@scholarsync.test` | Student, steps 1 to 7 |
| Applicant (Carolyn Hawkins) | `student@scholarsync.test` | Student, steps 8 to 13 |
| Returned applicant (Miguel Bautista) | `applicant4@scholarsync.test` | Student, steps 14 and 15 |
| Scholar due to renew (Carmela Villanueva) | `scholar@scholarsync.test` | Student, steps 16 to 18 |
| Scholar on hold (Elena Garcia) | `scholar3@scholarsync.test` | Student, steps 19 to 21 |
| CEAA staff (Krista Kelley) | `staff@scholarsync.test` | Program staff |
| CEAA head (Shannon Briggs) | `head@scholarsync.test` | Program head |
| Scholarship office (Jessica Tate) | `office@scholarsync.test` | Scholarship office |

The LANI accounts (`lani.staff@scholarsync.test`, `lani.head@scholarsync.test`) see the same screens for the LANI
program.

Captured on 26 November 2026 at 1280 × 800 in the light theme, as full-page screenshots.
