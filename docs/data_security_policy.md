# Data Security Policy

**Project:** Canadian Housing Data Governance & Quality Framework
**Scope:** Access control, data classification, masking, and access auditing for the
`cmhc_housing_starts_2018_2023` dataset and any future data sources onboarded to the framework.
**Status:** Independent portfolio project. Roles, systems, and incident narratives are illustrative.

---

## 1. Purpose & scope

This policy defines how data in the project is classified by sensitivity, who may access each
sensitivity level, how restricted values are masked, and how access is recorded. It applies to the
published housing dataset and to any additional source registered in the classification register.

The controls are implemented as a **reusable, configuration-driven framework** (see the `security/`
folder), not as one-off logic tied to a single dataset.

---

## 2. Design rationale — why a framework, and why sample data

This housing dataset is **aggregate statistics** (province × month × dwelling type × intended market)
and contains **no personal information** — its data dictionary classifies every field `PII: No`, and
PIPEDA does not apply.

Rather than fabricate personal data to justify a security layer, security here is built as a
**reusable framework**. It protects this dataset's one `Internal` field (`AVERAGE_PRICE_CAD`) today,
and is demonstrated against a small, clearly-labelled **synthetic fixture**
(`security/sample_sensitive_records.csv`) to prove it handles `Confidential`/PII data — hashing,
partial masking, and column denial — when such sources are onboarded.

This mirrors how enterprise platforms apply one masking framework across many datasets of differing
sensitivity, and it keeps the real dataset free of invented data.

---

## 3. Sensitivity classification scheme

Every column is assigned one of three tiers, recorded in
[`security/data_classification.csv`](../security/data_classification.csv):

| Tier | Definition | Example fields |
|------|------------|----------------|
| **Public** | Released or releasable as open data; no access restriction. | `REF_DATE`, `GEO`, `HOUSING_STARTS` |
| **Internal** | Not published at this grain; restricted to internal roles. | `AVERAGE_PRICE_CAD` (feeds mortgage-insurance thresholds — OSFI B-20 indirect) |
| **Confidential** | Sensitive or personal data; tightly restricted. | `APPLICANT_NAME`, `APPLICANT_EMAIL` (sample fixture only) |

---

## 4. Roles & access model

The project's six governance roles map onto four access patterns. Full decisions are held in
[`security/access_control_matrix.csv`](../security/access_control_matrix.csv).

| Role | Access pattern | Public | Internal | Confidential | Export |
|------|----------------|--------|----------|--------------|--------|
| Chief Data Officer (CDO) | Full | ALLOW | ALLOW | ALLOW | Yes |
| Data Owner | Full | ALLOW | ALLOW | ALLOW | Yes |
| Data Steward | Operational | ALLOW | ALLOW | MASK | Yes |
| Data Custodian | Technical | ALLOW | MASK | MASK | No |
| Data Consumer | Restricted | ALLOW | MASK | DENY | Yes |
| Data Governance Office (DGO) | Restricted | ALLOW | MASK | DENY | Yes |

- **ALLOW** — the real value is shown.
- **MASK** — a transformed value is shown (see §5).
- **DENY** — the column is removed entirely, so it appears neither on screen nor in any export.

The model follows **least privilege**: each role receives the minimum access its responsibilities
require. The Data Custodian, for example, manages infrastructure and therefore sees schema and volume
but not business-sensitive values, and cannot bulk-export data.

---

## 5. Masking methods

When a decision is MASK, the method is resolved from
[`security/masking_policy.csv`](../security/masking_policy.csv):

| Method | Behaviour | Example |
|--------|-----------|---------|
| `none` | Value unchanged (Public data). | `764` → `764` |
| `band` | Numeric value rounded into a range. | `743086.78` → `$700K-$800K` |
| `hash` | One-way SHA-256, truncated; deterministic. | `Avery Chen` → `9cca17a2` |
| `redact` | Replaced with a fixed token. | any → `[RESTRICTED]` |
| `partial` | Only a fragment shown. | `jane@x.ca` → `j***@x.ca` |

**Resolution order (default-plus-override):** the engine first looks for a column-specific rule, then
falls back to a wildcard default for the sensitivity tier (`*, *, Internal → redact`;
`*, *, Confidential → hash`). This means **a newly classified column is protected immediately by its
tier default, before any column-specific rule is written** — the core of the framework's scalability.

Banding is used for financial values because it preserves analytical usefulness (trends and
comparisons remain visible) without exposing the exact figure. Hashing is deterministic so masked
values can still be counted or joined without revealing identity.

---

## 6. Enforcement

Masking is applied inside the engine's `apply_masking()` function, not in the user interface. Because
the masked dataframe is what gets both displayed *and* exported, **masking cannot be bypassed by
downloading**. Where a role's export permission is `No`, the download control is withheld entirely.

Enforcement points in the dashboard:

- **Exception Explorer** — real housing records; `AVERAGE_PRICE_CAD` is banded for restricted roles.
- **Data Security tab** — the synthetic fixture, demonstrating hashing, partial masking, and denial of
  the Confidential/PII columns.

---

## 7. Audit & monitoring

Every masking operation appends an entry to `security/access_audit_log.csv` capturing: timestamp,
user, role, action, dataset, rows returned, columns masked, columns denied, columns unclassified, and
export permission. Auditing happens inside the engine, so **access and logging cannot be separated** —
every access is recorded by construction.

- **Retention policy:** the log is capped at **1,000 entries** (rotation keeps the most recent),
  so it cannot grow unbounded.
- **Runtime artifact:** the log is treated as output, not source — it is git-ignored and regenerated
  at runtime.
- **Identity caveat:** this demonstration has no authentication, so the **role** is the meaningful
  signal and the user field records the session. With real authentication the user field becomes the
  authenticated username, with no other change to the design.

---

## 8. Scalability — onboarding a new source

Adding a new data source requires **configuration, not code**:

1. **Classify** — add the source's columns to `data_classification.csv` with their sensitivity tiers.
2. **Set policy (optional)** — add column-specific masking rules to `masking_policy.csv`; otherwise the
   tier defaults apply automatically.
3. **Protected** — the same engine now enforces access control on the new source; no engine changes.

The engine references no column or dataset by name in its logic, which is what makes this possible.

---

## 9. Production patterns not implemented

This project demonstrates the governance patterns. A full production deployment would add:

- **Authentication & identity** — real login / SSO, replacing the role selector; the audit log would
  then record authenticated usernames.
- **Backed audit store** — database or append-only store, or streaming to a SIEM, replacing the CSV
  (which does not survive restarts on ephemeral hosting).
- **Encryption** — at rest and in transit, with managed key rotation.
- **Row-level security** — record-level filtering by scope (e.g. a province-scoped role). Not
  implemented here because the current role model has no scoped role; forcing it would model a role
  that does not exist.
- **Keyed / salted hashing** — for real personal data, to resist reversal, replacing the plain
  deterministic hash used for demonstration.
- **Key management** — a managed KMS for secrets and encryption keys.

Listing these boundaries explicitly is deliberate: the framework is honest about where the
demonstration ends and production begins.

---

## 10. Standards alignment

- **DAMA-DMBOK — Data Security knowledge area.** This framework raises the project's Data Security
  maturity from *Initial* toward *Managed* (see [`governance/dama_alignment.csv`](../governance/dama_alignment.csv)),
  covering classification, access control, masking, and audit.
- **Least privilege & access control** — consistent with access-control principles in ISO/IEC 27001.
- **Privacy** — PIPEDA is not applicable to the published aggregate dataset (no personal data); the
  Confidential-tier controls exist to handle personal data if a source ever carries it.

---

## 11. File reference

| File | Role |
|------|------|
| `security/data_classification.csv` | Sensitivity tier of every column, per dataset |
| `security/access_control_matrix.csv` | Role × tier → ALLOW / MASK / DENY, with justification |
| `security/masking_policy.csv` | Masking method per column/tier (defaults + overrides) |
| `security/masking_engine.py` | The engine — `apply_masking()`, methods, audit logging |
| `security/sample_sensitive_records.csv` | Synthetic fixture demonstrating the Confidential tier |
| `security/access_audit_log.csv` | Access audit trail (runtime artifact, git-ignored) |
| `docs/data_security_policy.md` | This policy |
