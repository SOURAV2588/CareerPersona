# Sourav Ghosh — Complete Career Profile

*A comprehensive, structured record of professional experience, skills, and credentials.
Written to serve as a project artifact and as a datasource for AI/retrieval use — statements
are kept self-contained so individual sections remain meaningful when read in isolation.*

**Provenance:** compiled from Sourav's resume (positioning pass complete, 16 Aug 2026),
Naukri profile, personal site (souravghosh.in), the career-positioning context handoffs
(v1 and v2), the `CLAUDE.md` amendments file, and direct interview. Where earlier documents
contained errors, this document records the **corrected, accurate version** (see §12).
Figures still to be gathered are marked **[TBD]** rather than estimated.

**Snapshot date:** 17 August 2026. Experience totals are anchored to a start date
(November 2016) so they remain computable over time.

**Status of this revision:** supersedes the pre-resume-pass version of this file. Certification
status, location, the Business Alerts narrative, and several framings have materially changed —
see §13 for a change log.

---

## 1. Profile at a glance

| Field | Value |
|-------|-------|
| Full name | Sourav Ghosh |
| Current title | Senior Associate, Publicis Sapient |
| Function | Backend engineer (backend + system design) |
| Total experience | ~9 years 9 months, continuous since November 2016 |
| Domain specialisation | RegTech — regulatory reporting, compliance & wealth-management platforms (~4 yrs 9 mo) |
| Core stack | Java, Spring Boot, Python, SQL, Microservices, AWS, Airflow |
| Certifications | AWS Certified Developer – Associate (DVA-C02), Jun 2026 — **the only valid credential** |
| Career target | Staff Engineer (broader backend + system design lean) |
| Personal site | souravghosh.in (in build) |
| Current location | Kolkata, India (relocated April 2026); works remotely with the Bangalore team |
| Education | B.Tech, Electrical Engineering — Siliguri Institute of Technology, Aug 2012 – Jun 2016, CGPA 8.23 |
| Contact | souravghosh2588@gmail.com · +91 84364 22588 · LinkedIn `souravghosh2588` · GitHub `SOURAV2588` |

*Contact note: the LinkedIn and GitHub values above are the handles as printed on the resume.
Full canonical URLs should be confirmed once before they are published on the site.*

---

## 2. Professional summary

Sourav Ghosh is a backend engineer with approximately nine years and nine months of continuous
experience. His core technical stack is Java, Spring Framework/Spring Boot, Python, and SQL,
working with microservices architecture and cloud-native development on AWS. For the most
recent ~4 years 9 months he has worked in RegTech — regulatory reporting and compliance
platforms in financial services, where incorrect output carries regulatory consequences and
compounds across future reporting dates.

He works as an end-to-end owner of single tracks: design, development, release and change
control, and production incident response. He has designed a workflow that became the
program's standard pattern and built an internal capability adopted by seven projects. His
demonstrated preference is for accuracy over impressiveness — he consistently chooses the
smaller true claim over the larger inflated one, and frames his work in terms of decisions and
tradeoffs rather than tasks completed.

**Resume summary (locked wording, for consistency across artifacts):**

> Senior Software Engineer with 9+ years of experience in Java, Spring Framework, and
> Microservices, along with 4+ years in Python, AWS, and Airflow. For the last 4+ years,
> building regulatory reporting and compliance platforms in financial services. End-to-end
> owner of single tracks — design, development, release, and production incidents — with
> designs adopted as the program-wide standard.

---

## 3. Career objective

Sourav is targeting **Staff Engineer** roles with a broader backend and system-design lean.
His case for that level rests on three axes of demonstrated work: designing correct
high-stakes systems (depth), creating capability the whole organisation adopts (leverage),
and owning systems end to end including production incidents (reliability). See §6 for the
detailed achievements supporting each axis.

He does not print the title "Staff Engineer" on any document — the work is described and the
evidence is left to argue for the level.

---

## 4. Employment history (detailed)

Listed reverse-chronologically. Every documented responsibility and achievement is included.

### 4.1 Publicis Sapient — Senior Associate
**Duration:** November 2021 – Present (~4 years 9 months)
**Location of record:** Bangalore, India (Sourav works remotely from Kolkata since April 2026)
**Domain:** Regulatory Technology (RegTech) — regulatory reporting and compliance
**Ownership model:** single-track owner — workflow design, development, release management,
change control, and incident management.

#### Project: Vendor Integration & Forensic Research Tool
**Duration:** January 2025 – Present
- **Sole engineer owning design, ETL implementation, release, and change control end to end**,
  delivering **16 user stories** to build a new forensic data-processing system with
  **Python, AWS, Airflow, and PostgreSQL**. *(Framing note: "sole engineer owning… end to end"
  is the canonical phrasing — ownership framing, not headcount framing.)*
- Designed and implemented **ETL workflows and automation pipelines in Airflow**, enabling
  secure, scalable ingestion and transformation of investigation data.
- Established **change control and release process**, ensuring production readiness and
  reducing deployment risk.
- Completed 10 user stories on an existing platform built with **Java, Spring, AWS, and
  GraphQL**.
- Migrated the **Forensics track to a new Linux OS version** ahead of AWS decommissioning of
  the prior version, including updates to **CloudFormation templates and setup scripts**.
  *(Accuracy note: this was part of an organisation-wide migration effort. Sourav executed it
  for his own Forensics track, following practices defined by the lead engineer; he did not
  lead the overall migration. See §12.)*
- Removed **ElasticSearch dependencies** and deprecated outdated modules, reducing technical
  debt.
- Debugged failures by integrating with cross-team APIs, improving system stability and
  maintainability.

#### Project: Regulatory Technology (TRR)
**Duration:** November 2021 – December 2024
- Delivered **320+ user stories** across **6 major regulatory regimes**, including **2
  Refits**, to comply with evolving regulatory changes.
- Built and optimised **20+ Airflow DAGs** orchestrating large-scale reporting pipelines on
  **AWS (S3, ECS, EC2, CloudWatch)**.
- **Positions workflow (pillar 1):** designed end to end a positions workflow aggregating
  notional/quantity across related trades, tracking state transitions, and reporting to an
  external vendor under a regulatory SLA — where one wrong report cascades into every future
  reporting date. The design became the program's standard pattern, the first of its kind on
  the team. (Full narrative: §6.1.)
- **Business alerting (pillar 2):** built the program's business-alerting capability as an
  internal Python package — small composable methods, alert delivery abstracted behind one
  concrete workflow. **Adopted across 7 projects: all 6 regulatory regimes plus the forensics
  track.** (Full narrative: §6.2.)
- **Production incidents (pillar 3):** handled production incidents on the track from recovery
  through permanent fix — including a weekend restoration shipped via emergency change
  management. (Full narrative: §6.3.)
- Diagnosed the team's **slow Jenkins builds** — unit tests were waiting through real retry
  delays — and eliminated the waits by mocking the retry mechanism, **cutting build times
  40–60%**.
- Delivered consistently reliable code with **95%+ unit-test coverage** (measured via
  **SonarQube**).
- Used **Pandas** for data transformations. *(NumPy was also used but is deliberately kept off
  the resume — no 90-second story behind it. See §12.7.)*

### 4.2 Dassault Systèmes — Development Engineer
**Duration:** November 2018 – November 2021 (3 years)
**Location:** Pune, India
**People:** Mentored a junior engineer through code reviews and design discussions, which
shaped his approach to code review and shared ownership of a codebase.

#### Project: IS Requirements
**Duration:** November 2018 – August 2020
- Delivered **40+ features/enhancements in Java** for a Jira-like requirements/defect
  management tool on the **3DEXPERIENCE Platform**, using **REST APIs and ENOVIA APIs/DB**.
- Migrated **1,300+ legacy requirements** into the platform, enabling adoption by
  **12–15 internal product teams**. *(The resume and Naukri profile use the conservative
  "10+ product teams". Both are true; do not exceed 12–15 anywhere.)*
- Proposed and implemented **design optimisations** that improved maintainability and system
  performance.
- Drove **end-to-end ownership** of development, release cycles, and production support as the
  sole developer on the project.

#### Project: My Offer
**Duration:** August 2020 – November 2021
- Built **15+ catalog features in Java** for the My Offer digital marketing tool on the
  **3DEXPERIENCE Platform**, using **REST APIs and ENOVIA APIs/DB** — showcasing Dassault's
  offerings and improving catalog search, browsing, and product-detail presentation.
- Improved application stability and performance through API optimisations and design
  improvements.
- Collaborated with **UI, Content, and QA teams** to deliver features and resolve production
  issues in an agile environment.

*(Note: IS Requirements and My Offer ran sequentially — IS Requirements ended August 2020,
after which My Offer began. They were not concurrent.)*

### 4.3 Tata Consultancy Services — Assistant System Engineer
**Duration:** November 2016 – November 2018 (2 years)
**Location:** Pune, India

#### Project: Shared Printing Platform
- Developed a **Spring Batch module** with tuned job strategies for the platform's batch
  processing.
- **Executed the AngularJS → Angular 2 migration as the sole developer on the feature**,
  modernising the platform's frontend. *(Canonical framing: never "led" — no team existed;
  never "contributed" — it undersells solo ownership.)*
- Maintained **80%+ code coverage** with **JUnit and Mockito**; continuously improved quality
  using **SonarQube**, reducing vulnerabilities and code smells by **70%**.
- Enhanced application performance and maintainability through multiple design and optimisation
  initiatives.

---

## 5. Employment timeline (chronological)

| Period | Company | Title | Location |
|--------|---------|-------|----------|
| Nov 2016 – Nov 2018 | Tata Consultancy Services | Assistant System Engineer | Pune, India |
| Nov 2018 – Nov 2021 | Dassault Systèmes | Development Engineer | Pune, India |
| Nov 2021 – Present | Publicis Sapient | Senior Associate | Bangalore, India (remote from Kolkata since Apr 2026) |

Total: continuous employment, no gaps. RegTech specialisation begins November 2021.
Python / AWS / Airflow experience begins November 2021 → **"4+ years"** is the accurate claim
until November 2026, when "5 years" becomes literally true.

**Prepared one-liner if asked about location:** *"I moved to Kolkata in April and work
remotely with the Bangalore team."*

---

## 6. Signature achievements (detailed narratives)

These three represent Sourav's strongest, most senior-level work, each demonstrating a
different capability. They are the spine of every career artifact — resume, Naukri profile,
and portfolio site all carry the same three pillars.

### 6.1 Positions Workflow — system design / depth
*"I design correct, high-stakes systems."*

Sourav designed, end to end, a positions-reporting workflow in the regulatory-technology
domain. The system aggregates **notional and quantity values across trades sharing the same
id**, tracks which positions each trade currently holds, and drives the **state transitions**
required to keep reporting accurate across a wide range of scenarios. Aggregated results are
reported to an **external vendor under a regulatory SLA**.

The stakes were high and compounding: incorrect positions reporting does not just fail once —
it **cascades into errored positions for all future reporting dates**, so accuracy was
paramount. Incorrect reporting also triggers alerts and involves multiple business
stakeholders across individual tracks.

He designed the state model himself. It was the **first time the pattern existed on his
team**, and the design **became the program's standard pattern**.

**Metrics [TBD]:** trade volume/throughput, SLA target window, number of tracks that adopted
the design, regulatory framework name.

### 6.2 Business Alerts — leverage / force multiplication
*"I create capability the whole organisation adopts."*

**This is a new-capability story, not a speed story.** Business alerting was a requirement
spanning every regulatory regime, and no shared implementation existed. Sourav built the
program's business-alerting capability as an **internal (private) Python package**: the flow
is coded as **small composable methods**, and **alert delivery is abstracted behind one
concrete workflow**, so adding an alert for a new regime is configuration rather than surgery.
Debugging isolates to small, testable methods.

Because the package was designed that way, implementing alerts for a regime takes roughly a
**single day**. It was **adopted across 7 projects — all 6 regulatory regimes plus the
forensics track**. Adoption by the forensics track matters: that is a different project
entirely (one Sourav later joined), so the design outlived its original context.

**Correction on record:** an earlier version of this profile described this as re-architecting
a painful JSON-driven feature and claimed implementation effort "dropped to" ~a day. That
implies a prior slower state that never existed. There is **no before/after claim** here.
See §12.5.

**Metrics [TBD]:** none outstanding for the core claim; optional detail is the number of alert
types now in use.

### 6.3 The Sunday Production Incident — reliability / ownership
*"Trusted to own it end to end, including when it breaks."*

A production **data-enrichment step broke on a Sunday morning**. The root cause was a database
read method that used an **unbatched `IN` clause**; it could not handle the day's large number
of trade ids and hit a hard SQL limit on list size.

Sourav owned the response. He diagnosed the root cause, then **restored service** by
repurposing an existing per-trade feature: he identified all trade ids for that day, divided
them into **batches of 500**, and ran the workflow multiple times — capturing all trades
within **6–7 runs**. Work began Sunday morning and completed by mid-afternoon.

He then closed the underlying flaw permanently: he **filed the bug the same Sunday**, **fixed
the batching properly in the read method on Monday**, and **shipped the permanent fix to
production that same Monday via emergency change management**. Full detect → recover →
permanent-fix cycle completed within roughly 48 hours, including a weekend.

*Written materials carry only the generic version ("handled production incidents from recovery
through permanent fix — including a weekend restoration shipped via emergency change
management"). The full arc is interview material. "First responder" was rejected as inflated —
he is not always first responder.*

**Metrics [TBD]:** approximate volume of trade ids processed that day.

---

## 6a. Interview pocket details — deliberately NOT in written materials

*Held back so there is something to demonstrate live. Do not publish these to the site,
resume, Naukri, or any public artifact. A pocket detail only works if the written claim
survives without it.*

1. **Business Alerts** — the ~1-day-per-regime implementation figure. Delivery: when asked
   "why did it spread to 7 projects?" → "each regime's implementation took about a day."
   *(Open decision: the portfolio site is the long-form case and may carry this figure. Decide
   once when writing final pillar copy; do not let site and resume contradict each other.)*
2. **Jenkins** — the full mechanism: tests covering a retry feature were *actually sleeping*
   through 3 retries × 30 s = 90 real seconds per test; nobody on the team had diagnosed it;
   the fix was a mock decorator exercising the retry logic without the waits.
3. **Sunday incident** — the full arc in §6.3. Written materials carry only the generic
   version.

---

## 7. Skills & technologies (exhaustive)

*This is the complete inventory. It is deliberately broader than what appears on the resume or
in Naukri's IT-skills table — see §7a for what was filtered out and why.*

### Programming languages
- **Java** — primary language across ~9 years. Specific competencies: Java 8 features
  (streams, optionals, functional interfaces); multi-threading and concurrency via the
  `java.util.concurrent` APIs; memory profiling and heap analysis.
- **Python** — data processing, workflow tooling, internal packages, testing (~4 yrs 9 mo,
  since Nov 2021).
- **SQL** — query work, schema design, batching within engine limits (see §6.3).

### Frameworks & backend
- Spring Boot, Spring Framework
- Spring Batch
- Hibernate / JPA
- RESTful web services
- Microservices architecture
- GraphQL
- ENOVIA APIs/DB (Dassault 3DEXPERIENCE platform)

### Data & pipelines
- Apache Airflow (DAG orchestration for reporting pipelines)
- Pandas (data transformation)
- NumPy (computational efficiency)
- ETL workflow design
- PostgreSQL

### Cloud & infrastructure (AWS)
- EC2, S3, ECS, CloudWatch, CloudFront, IAM, CloudFormation
- Cloud-native application development
- Certificate rotation / encryption practices
- Linux (OS migration, setup scripts)
- Docker

### AI-assisted engineering (current, hands-on)
*Careful language matters here: these are tools used in daily engineering work, not production
AI systems he has built. Claim "hands-on with", never "built".*
- GitHub Copilot
- Claude Code
- Agentic development workflows
- MCP (Model Context Protocol)
- LLM output evaluation

### Frontend (earlier career)
- AngularJS, Angular 2 (migration work at TCS, 2016–2018)

### Engineering practices
- System design & architecture
- CI/CD (Jenkins; 40–60% build-time reduction)
- Test coverage & quality gates (JUnit, Mockito, SonarQube; sustained 80–95%+ coverage)
- Release management & change control (including emergency change management)
- Incident management & production support
- Code review and shared code ownership
- Technical mentorship
- Agile delivery

### 7a. Skill-claim accuracy notes
- **Microservices — last used 2021.** The Python services at Publicis Sapient share a single
  database and operate within one pipeline; that is not a true microservices architecture.
  The defensible microservices experience is the Java/Spring work up to 2021. This prevents a
  common and easily-exposed overreach in interviews.
- **Removed from the Naukri IT-skills table for insufficient defensible depth:** Kafka, Docker,
  Spring Framework, PostgreSQL. They remain accurate as *exposure* and stay in this inventory;
  they are not claimed as rated skills with years attached.
- **ENOVIA and AngularJS removed from Naukri Key Skills** — they are real experience but
  attract mismatched recruiter searches.
- **Naukri IT Skills, final 10:** Java, Python, Spring Boot, Hibernate, Microservices, AWS,
  Apache Airflow, SQL, RESTful Web Services, Jenkins.
- **Skills bullets for the portfolio site are still to be written** — 18 capability claims,
  no adjectives, specificity carrying the claim, each interview-defensible.

---

## 8. Certifications

### Held (valid)
- **AWS Certified Developer – Associate (DVA-C02)**
  - Issuer: Amazon Web Services
  - Issued: **June 2026** · Valid 3 years (to Jun 2029) · Credly verification link **[TBD]**
  - **This is the only valid credential.** Exam scores are never shown anywhere — they read
    junior.

### Lapsed (do not claim)
- **AWS Certified Solutions Architect – Associate** — issued May 2023, **lapsed May 2026**
  (3-year validity).
- **AWS Certified Cloud Practitioner** — issued June 2021, **lapsed**.

**Consequence:** no "2× AWS Certified" or "3× AWS Certified" phrasing anywhere — resume,
Naukri, site, LinkedIn. The correct header phrasing is **"AWS Certified"** (singular, no
count).

### Other learning
- Udemy course-completion certificates exist but are excluded from all career artifacts —
  they are completion receipts, not proctored credentials.

---

## 9. Consolidated metrics

A single reference list of quantified results across Sourav's career.

| Metric | Context |
|--------|---------|
| 320+ user stories | Delivered across 6 regulatory regimes (Publicis Sapient, TRR) |
| 6 major regulatory regimes + 2 Refits | Regulatory coverage (Publicis Sapient, TRR) |
| 20+ Airflow DAGs | Reporting pipeline orchestration on AWS (Publicis Sapient, TRR) |
| 95%+ unit-test coverage | Publicis Sapient, TRR (via SonarQube) |
| 40–60% | Reduction in Jenkins build times (Publicis Sapient, TRR) |
| 16 user stories, sole engineer, end-to-end ownership | New forensic system (Publicis Sapient, Vendor Integration) |
| 10 user stories | Existing Java/Spring/AWS/GraphQL platform (Publicis Sapient) |
| **Adopted across 7 projects** | Business-alerting package: 6 regulatory regimes + forensics track |
| Program's standard pattern, first of its kind on the team | Positions workflow design |
| Batches of 500, 6–7 runs, ~48h to permanent fix | Sunday production incident recovery |
| 1,300+ legacy requirements migrated | Used by 12–15 product teams; stated as "10+" on resume/Naukri (Dassault, IS Requirements) |
| 40+ features/enhancements | Dassault, IS Requirements |
| 15+ catalog features | Dassault, My Offer |
| 80%+ code coverage; 70% reduction in vulnerabilities/code smells | TCS, Shared Printing Platform |
| ~1 day implementation per regime | Business Alerts — **pocket detail, off written materials** (§6a) |

Metrics marked **[TBD]** elsewhere (positions trade volume, SLA target, Sunday incident trade
volume) are still pending.

---

## 10. Professional approach (observed & self-evidenced)

Documented traits consistently demonstrated in Sourav's work and decision-making:

- **Accuracy over impressiveness.** Repeatedly chooses the smaller accurate claim over a
  larger inflated one; proactively flags and corrects overstatements about his own scope
  (he flagged "first responder" as inflated himself, and chose "10+ product teams" over
  "12–15" when both were true).
- **Ownership orientation.** Takes systems through their entire lifecycle — design,
  development, release, and incident response — and has been the sole or primary contributor
  on multiple systems.
- **System-design focus.** Draws attention to how services communicate, scale, and fail;
  prefers to design a problem out rather than patch around it.
- **Judgment over recall.** Frames technical work in terms of decisions and tradeoffs rather
  than tools used or tasks completed.
- **Force-multiplier instinct.** Produces patterns and capabilities that other engineers and
  tracks adopt, improving org-wide throughput rather than only his own.
- **Reliability under pressure.** Owns incident response calmly, diagnoses root cause, and
  closes failure classes permanently rather than only recovering.

**Known bias, both directions:** he undersells genuinely hard work ("maybe it wasn't that
hard" — said about Staff-level systems), and drifts toward adjectives when writing about his
own abilities. The cure for both is identical: state the specific thing. **Over-compression is
the larger risk** — left unchecked, his instinct strips out exactly the judgment details that
function as seniority signals.

---

## 11. Data gaps (to be completed)

Items still outstanding:

- **Pillar metrics** — Positions workflow (trade volume, SLA target window, adopting track
  count, regulatory framework name); Sunday incident (trade-id volume).
- **Credly verification link** for the DVA-C02 credential, and the badge image for the site's
  `badges/` folder.
- **Skills bullets** — 18 final, interview-defensible capability statements for the portfolio
  site (still placeholder).
- **Canonical contact URLs** — exact LinkedIn and GitHub URLs to publish; decision on the
  "Based in India · Open to remote" line.
- **GitHub repo quality review** — gates whether personal projects return to the resume,
  Naukri, and site.
- **Naukri open items** — (1) verify no third-party contact details carried over from 2021
  templates into existing project entries; (2) confirm Java "last used 2026" once
  legacy/decommission work is verified.
- **Languages spoken**, and any additional publications or talks.

---

## 12. Data-accuracy notes

Corrections applied when compiling this record, and deliberate exclusions:

1. **Linux OS migration — corrected from "led" to "executed for own track."** An earlier
   resume stated Sourav *led* the Linux OS migration. It was an organisation-wide effort; he
   performed it for his Forensics track, following practices the lead engineer had already
   defined.
2. **Dassault project dates — corrected.** An earlier combined resume card mis-dated the
   Dassault tenure as 08/2020–11/2021, understating it by ~21 months and implying an
   employment gap. Correct tenure is **November 2018 – November 2021**, with IS Requirements
   (Nov 2018 – Aug 2020) followed by My Offer (Aug 2020 – Nov 2021).
3. **"Mentored a junior engineer" — precise wording.** People-leadership at Dassault was
   mentoring a single junior engineer through code reviews and design discussions. Recorded as
   mentoring, never "led a team."
4. **Reference contact — deliberately excluded.** A colleague's name and mobile number
   appeared as a reference on one resume card. That is third-party personal data; it is absent
   from the current resume and from this document. **Circulating copies (Naukri, LinkedIn,
   agency databases) must still be purged.**
5. **Business Alerts — framing corrected (NEW).** Previously described as re-architecting a
   painful JSON-driven feature, with implementation effort that "dropped to" ~a day. This
   implies a prior slower state that never existed. It was a **brand-new capability**; there is
   no before/after claim. See §6.2.
6. **Certifications — status changed (NEW).** SAA (May 2023) and Cloud Practitioner (Jun 2021)
   have both lapsed. DVA-C02 (Jun 2026) is the only valid credential. Any "2× AWS Certified"
   phrasing is now false and must be removed wherever it appears.
7. **NumPy — kept off the resume (NEW).** Used in practice, but there is no 90-second story
   behind it, and every claim is an interview promise. Recorded here, omitted there. The same
   test removed the "high-performance, fault-tolerant workflows" filler bullet — its content
   was absorbed into the Airflow DAG bullet.
8. **"First responder" — rejected as inflated (NEW).** He is not always first responder. The
   accurate framing is ownership from recovery through permanent fix.
9. **Location — updated (NEW).** Relocated to Kolkata in April 2026, working remotely with the
   Bangalore team. Resume header says Kolkata; both Publicis Sapient entries say Bangalore
   (location of record).
10. **Angular migration — canonical framing (NEW).** "Executed as the sole developer on the
    feature." Never "led" (no team existed); never "contributed" (undersells solo ownership).
11. **Python/AWS/Airflow tenure (NEW).** "4+ years" is the bulletproof claim until November
    2026, when "5 years" becomes literally true. Naukri years were corrected from 5 to 4 to
    match.
12. **Microservices claim scoped (NEW).** See §7a — last genuine microservices work was 2021.

---

## 13. Change log for this revision (17 Aug 2026)

What changed from the previous version of this file:

- **§1** — experience 9y8m → 9y9m; RegTech 4.6 → 4.75 yrs; certifications replaced with
  DVA-only; location, education, and contact details filled in (previously [TBD]).
- **§2** — totals updated; locked resume summary wording added.
- **§4.1** — Publicis Sapient location added; Forensics bullets rewritten to the canonical
  ownership framing; the three pillars added to the TRR project (they were previously
  described only in §6, so the employment section and the achievements section disagreed);
  Jenkins bullet added with the accurate mechanism; filler "high-performance… fault-tolerant"
  bullet removed.
- **§4.2 / §4.3** — Dassault and TCS bullets aligned to canonical resume phrasings; the "10+
  vs 12–15" decision recorded.
- **§5** — locations added to the timeline; Python/AWS tenure rule and the location one-liner
  added.
- **§6.1** — "adopted as standard across all tracks" → "became the program's standard pattern,
  first of its kind on the team."
- **§6.2** — rewritten. The JSON/before-after framing was wrong; this is a new-capability
  story adopted across 7 projects.
- **§6a** — new section: interview pocket details, marked not-for-publication.
- **§7** — AI-assisted engineering tools added; Spring Framework, Hibernate, RESTful web
  services made explicit; new §7a records the skill-claim scoping decisions from the Naukri
  pass.
- **§8** — rewritten for DVA-only, with the lapsed credentials recorded so they are not
  re-claimed by accident.
- **§9** — metrics table corrected (7 projects, standard pattern, 10+ vs 12–15, pocket-detail
  marking).
- **§10** — over-compression named as the primary risk.
- **§11** — closed gaps removed; live gaps (including the two Naukri items and the GitHub
  review) added.
- **§12** — eight new accuracy notes (items 5–12).

---

## 14. Related artifacts

All career materials share one positioning narrative — a change to framing in one propagates
to the others.

| Artifact | Status |
|----------|--------|
| Resume (`My_Resume.pdf`) | Positioning pass complete, 16 Aug 2026. Canonical. |
| Naukri profile | Comprehensive update complete; two open verification items (§11). |
| Portfolio site (souravghosh.in) | Scaffold built (plain HTML/CSS/JS); Days 6–7 of build plan remain; skills bullets still placeholder. |
| `CLAUDE.md` | Site build spec — amendments pending (cert section, alerts copy, location). |
| `CLAUDE.react.md` | React migration architecture, documented for later. |
| `CONTEXT-HANDOFF-CAREER-POSITIONING-v2.md` | Portable context brief; supersedes v1. |
| Interview story bank | Eight stories in spoken form, pocket details marked, question-type → story mapping. |
| This file | AI/retrieval datasource. **Contains §6a pocket details — do not feed verbatim into any public-facing generator.** |
