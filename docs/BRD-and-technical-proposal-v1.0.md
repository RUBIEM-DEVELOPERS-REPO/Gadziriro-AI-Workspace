# Gadziriro AI Workspace — Business Requirements & Technical Proposal

| | |
| --- | --- |
| **Version** | 1.0 |
| **Date** | 6 October 2026 |
| **Prepared by** | Aiia |
| **Status** | For approval |
| **Supersedes** | Design draft v0.2 and BRD draft of 5 October 2026 |

Gadziriro AI Workspace lets a company build, adjust and test its own AI models on its own computers, so private data never has to leave the building. This document has two parts: Part A says what the business needs the product to do (the BRD), and Part B proposes how we will build it.

> **Repository note.** This file is the approved source document, committed for traceability.
> The Phase 0 implementation in this repo maps to the Phase 0 Must requirements in section 6;
> see `docs/phase-0-acceptance-tests.md` for the pass/fail mapping and `docs/adr/` for
> decisions on the section 14 open items.

## What changed in version 1.0

| Area | Gap in the first draft | What version 1.0 adds |
| --- | --- | --- |
| Commercial | No licensing model, pricing or support tiers | Commercial model options and support tiers (section 10) |
| Requirements | No way to check when a requirement is "done" | Acceptance criteria approach and phase exit criteria (sections 6 and 12) |
| Security operations | No incident response, patching, SBOM, key rotation or recovery targets | Security architecture (section 21), new requirements FR-38, FR-41, NFR-15 to NFR-18 |
| Compliance | No DSAR, DPIA, ROPA, agreement templates or claim review | Compliance and legal section with a legal review gate (section 9) |
| Data governance | Labels, retention and deletion not enforced end to end | Data governance service and section (section 22) |
| Model governance | No model cards, bias checks, red-teaming or licence checks | New Model Studio features (section 19), FR-36, FR-37, FR-48 |
| Technical | No API/CLI, monitoring, or plug-in security | Observability, API/CLI, plug-in signing (sections 17, 23, 24) |
| Delivery | No durations, team size or exit criteria | Phase estimates, exit criteria and team size (sections 12 and 13) |
| Go-to-market | No target customer, pilot criteria or sales approach | Go-to-market and pilot plan (section 11) |
| Usability | No accessibility or local language support | FR-43, FR-44, NFR-19 |

## Words used in this document

| Term | Plain meaning |
| --- | --- |
| AI model | A trained computer program that can answer questions, write text, or spot patterns. |
| LLM (large language model) | An AI model that reads and writes text, like a chatbot. |
| Weights | The learned numbers inside a model. They are the model's "knowledge" and are valuable company property. |
| Fine-tuning | Teaching an existing model new skills using the company's own examples, instead of building one from zero. |
| LoRA / QLoRA | Cheap ways to fine-tune: only a small add-on is trained, so a single graphics card is enough. QLoRA also shrinks the model first to save memory. |
| Quantize | Shrink a model so it runs on smaller, cheaper hardware, with a small loss in quality. |
| Merge / prune | Merge = combine two models into one. Prune = cut out parts of a model that do little, to make it smaller. |
| Notebook | A web page where a user writes code in small blocks (cells) and sees results straight away. Google Colab is a well-known example. |
| GPU | Graphics card. The expensive chip that does the heavy work of training and running AI models. |
| Self-hosted | Installed on the customer's own machines, not on our servers or the public cloud. |
| Single-tenant | Each customer gets their own separate installation. No two customers ever share one. |
| Egress | Data leaving the customer's machine for the internet. |
| Air-gapped | A machine with no internet connection at all. |
| Audit log | A record of who did what and when, that cannot be quietly changed. |
| SSO / MFA | SSO (single sign-on): staff log in with their normal company account. MFA (multi-factor authentication): a second login step, such as a phone code. |
| RBAC | Role-based access: what a person can see and do depends on their job role. |
| Lineage | A record of which data was used to make which model, so you can trace any model back to its sources. |
| Container | A sealed box on the computer that runs a program apart from everything else, so a mistake or bad code cannot spread. |
| Kubernetes / Slurm | Tools large companies use to share work across many computers. |
| API / CLI | API: a way for other software to control the workspace. CLI: typed commands, for scripts and automation. |
| Model card | A short fact sheet for a model: what it was trained on, its licence, test scores and known limits. |
| Bias / fairness check | Tests that show whether a model treats groups of people differently. |
| Red-teaming | Deliberately trying to make a model misbehave, to find weak spots before customers do. |
| DSAR (data subject access request) | A person's legal request to see, correct or delete the data an organisation holds about them. |
| DPIA (data protection impact assessment) | A written check of privacy risks before starting a new use of personal data. |
| ROPA (records of processing activities) | A register of what personal data is used, why, and by whom. GDPR requires one. |
| BAA / data processing agreement | Contracts that set out how a supplier must protect health data (BAA, under HIPAA) or personal data (data processing agreement, under GDPR and the ZW DPA). |
| ZW DPA | Zimbabwe's Cyber and Data Protection Act. |
| SBOM (software bill of materials) | A full list of the parts inside our software, so customers can check for known security problems. |
| CVE | A publicly listed security weakness in a piece of software. |
| RTO / RPO | RTO (recovery time objective): how long it may take to get running again after a failure. RPO (recovery point objective): how much recent work may be lost, measured in time. |
| Observability | Dashboards, logs and alerts that show whether the system is healthy. |
| SIEM | The customer's security monitoring system, which collects logs from many tools. |
| WCAG 2.1 AA | The common international standard for making software usable by people with disabilities. |
| Policy-as-code | Privacy and security rules written as versioned settings files, so every change is recorded and reviewable. |
| RACI | A chart showing who is Responsible, Accountable, Consulted and Informed for each area. |
| ICP (ideal customer profile) | A description of the customer we are best placed to win and serve. |

# Part A — Business Requirements Document (BRD)

## 1. Executive summary

Gadziriro AI Workspace is a self-hosted, single-tenant platform that lets regulated organisations build, fine-tune, evaluate and export their own text AI models without sensitive data leaving their premises. It starts on a single GPU server and scales to several servers, or to an existing Kubernetes or Slurm cluster, without changing the user screens or the privacy rules.

The same product serves SMEs with one GPU server and enterprises with many. It is designed from day one to support HIPAA, GDPR, SOC 2 and Zimbabwe's Cyber and Data Protection Act. The strictest common control applies everywhere by default. Zero egress is the default, and every approved transfer is logged and auditable.

We will validate with 2–3 pilot SMEs in Phase 1, reach enterprise readiness in Phase 3, and launch in Phase 4. Success means a paying pilot runs real fine-tuning on their own box and can prove to an auditor that no data left it.

## 2. The business problem

Companies want their own AI models, but the easy tools force them to send private data to someone else's cloud.

- **Privacy risk.** Hospitals, banks, insurers, government bodies and law firms hold personal data they are not allowed, or not willing, to upload to foreign cloud services.
- **Legal exposure.** Data protection laws, including Zimbabwe's Act, limit sending personal data across borders and require proof of who touched it.
- **No good local option.** Tools like Google Colab are easy to use but run in the cloud. Tools that run locally are scattered pieces that need a specialist team to join together and secure.
- **Cost and connectivity.** Cloud GPU bills are paid in foreign currency and grow every month. Internet links in the region can be slow or unreliable.
- **Weights are assets.** A fine-tuned model holds the company's know-how. Customers want to own it and keep it, not rent it.

The opportunity: one product that feels as easy as Colab, but where the code, data and models stay on the customer's own hardware, with the compliance evidence built in.

## 3. Business objectives and success measures

| # | Objective | How we measure it | Target | Owner | Checked |
| --- | --- | --- | --- | --- | --- |
| O1 | Keep customer data and models private | Bytes of data or weights sent out without an admin-approved path | Zero, shown in the "what left this machine" report | Security lead | Every release |
| O2 | Make setup easy for an SME | Time from unboxing to first notebook running on the GPU | Under 1 day, with no specialist | Product lead | Each pilot |
| O3 | Make model editing practical on one machine | A QLoRA fine-tune completes on one 24–48 GB GPU | Yes, for common open models up to the size the box can hold | ML lead | Phase 2 |
| O4 | Make compliance easier to prove | Exportable audit evidence packs | HIPAA, GDPR, SOC 2 and ZW DPA | Compliance lead | Phase 4 |
| O5 | Grow with the customer | Moving from one box to several needs no reinstall | Same UI, data and policies after scale-up | Architect | Phase 3 |
| O6 | Win first customers | Signed pilots after Phase 1 | 2–3 pilot SMEs | Sales lead | Phase 1 |
| O7 | Keep one product | Customer-specific code branches | None | Engineering lead | Continuous |

## 4. Scope

Version 1 covers text AI models (LLMs) end to end, on hardware the customer owns. Other model types get a plug-in path but not full support.

**In scope for v1:** Notebook workspace (Jupyter-compatible); model editing (fine-tune, evaluate, compare, merge, quantize, prune, export); versioned registry with lineage; users/roles/SSO/MFA + tamper-evident audit; privacy controls (no egress by default, labels, retention, purge); compliance policy packs (HIPAA, GDPR, SOC 2, ZW DPA); single-node to multi-node/K8s/Slurm; backup/restore with restore checks; optional online helpers (off by default); offline install via signed bundles; data ingestion from approved sources with labels; repeatable pinned environments; API and CLI; model cards, licence tracking, bias/fairness + red-teaming; incident response; observability; accessibility (WCAG 2.1 AA) + local languages.

**Out of scope for v1:** training very large models from zero; a public model store; running models for live end-users at scale (hand off to vLLM/TGI); multi-tenant shared installs; full vision/speech/tabular support (plug-in path only).

## 5. Stakeholders and user roles

| Role | Who they are | What they need |
| --- | --- | --- |
| Data scientist / ML engineer | Builds and adjusts models | Notebooks, GPU time, fine-tune templates, evaluations, model compare |
| Analyst / domain expert | Knows the business, writes less code | Form-based fine-tuning, simple evaluation screens, plain results |
| Workspace administrator | Runs the box for the customer | Easy install, user management, quotas, backups, updates |
| Compliance / data protection officer | Answers to regulators and auditors | Data labels, audit logs, transfer reports, evidence exports |
| Business sponsor | Pays for the product | Proof of value, cost control, risk kept low |

A full RACI is in the source proposal; each phase gate is signed off by the business sponsor and the technical lead.

## 6. Functional requirements

Priority: Must (needed for launch), Should (soon after), Could (nice to have). Phase refers to section 12.

| ID | Requirement | Priority | Phase |
| --- | --- | --- | --- |
| FR-01 | Users open notebooks in the browser, run code cell by cell and see charts, tables and text output. | Must | 0 |
| FR-02 | Existing Jupyter notebooks (.ipynb files) open without changes. | Must | 0 |
| FR-03 | Each user session runs in its own sealed container with access to an assigned GPU. | Must | 0 |
| FR-04 | Idle sessions give back their GPU automatically after a set time. | Must | 1 |
| FR-05 | Long jobs can be queued and run in the background, with quotas per user or project. | Must | 1 |
| FR-34 | Repeatable software environments with pinned package versions, served from the local mirror. | Must | 1 |
| FR-06 | Datasets and models are stored with version numbers and can be rolled back. | Must | 1 |
| FR-07 | Every model records which datasets, code, settings and hardware made it (lineage). | Must | 1 |
| FR-08 | Datasets carry a sensitivity label: public, internal, personal data, or health data (PHI). | Must | 1 |
| FR-09 | Every run is tracked so it can be repeated with the same result. | Must | 1 |
| FR-33 | Data can be brought in only from approved sources, and is labelled on the way in. | Must | 1 |
| FR-10 | Fine-tune models through ready templates (LoRA, QLoRA, full), using either a form or code. | Must | 2 |
| FR-11 | Test models against the customer's own question sets and compare versions side by side. | Must | 2 |
| FR-12 | Merge, shrink (quantize to GPTQ, AWQ or GGUF), trim (prune) and inspect models. | Should | 2 |
| FR-13 | Show a "diff" between two model versions: changed weights, score changes, sample answers. | Should | 2 |
| FR-14 | Show a visual map of how data, runs and models connect. | Could | 2 |
| FR-15 | Export models as safetensors, GGUF or ONNX and hand them to vLLM or TGI. | Must | 2 |
| FR-36 | Create a model card for every model: licence, training data, test scores and known limits. | Must | 2 |
| FR-48 | Check each model's licence and any export control limits before it is used or exported. | Must | 2 |
| FR-37 | Run bias and fairness checks and red-team tests on models. | Should | 3 |
| FR-16a | Small firms can use local accounts. | Must | 0 |
| FR-16b | Staff log in with their company accounts (SSO). | Must | 1 |
| FR-17 | Two-step login (MFA) and automatic logout after inactivity. | Must | 1 |
| FR-18a | Access set by role per project. | Must | 1 |
| FR-18b | Optional access rules per dataset. | Must | 3 |
| FR-19 | Tamper-evident logs of logins, data use, code runs, exports and admin actions. | Must | 0 |
| FR-41 | Customers hold their own encryption keys and can rotate them on a schedule or on demand. | Must | 1 |
| FR-20 | No outbound internet from user code by default. | Must | 0 |
| FR-21 | Exports of data or models need approval when policy says so, and are logged. | Must | 1 |
| FR-22 | Retention rules per dataset with scheduled deletion. | Must | 1 |
| FR-23 | Find every model a person's data was used in, and flag those models for retraining or removal. | Must | 1 |
| FR-24 | One-switch policy packs: hipaa, gdpr, soc2, zw-dpa. | Must | 2 |
| FR-38 | Incident response workflow, including breach notification steps and reports. | Must | 2 |
| FR-45 | DSAR workflow: find a person's data through lineage, then export or erase it. | Must | 2 |
| FR-25 | Admin report of everything that left the machine. | Must | 3 |
| FR-46 | Export records of processing (ROPA). | Should | 3 |
| FR-47 | DPIA templates and workflow. | Should | 3 |
| FR-26 | Export compliance evidence for auditors. | Should | 4 |
| FR-27 | Installer checks the hardware and reports which model sizes and methods it can handle. | Must | 0 |
| FR-28 | Backup and restore of settings, registry and storage. | Must | 1 |
| FR-29 | Local mirror of approved software packages and models. | Must | 1 |
| FR-31 | Licence key checked without needing the internet. | Must | 1 |
| FR-39 | Export metrics, logs and traces for monitoring. | Must | 1 |
| FR-42 | Backups are checked and test-restored automatically. | Must | 1 |
| FR-40 | Create support bundles with personal data removed, for troubleshooting. | Should | 2 |
| FR-30 | Signed updates, online or through offline bundles. | Must | 3 |
| FR-35 | API and CLI for automation, CI/CD and integration with other tools. | Should | 2 |
| FR-32 | Plug-in kit to add vision, speech and table-data model types. | Should | 4 |
| FR-43 | Screens meet WCAG 2.1 AA accessibility. | Should | 3 |
| FR-44 | Interface available in English, Shona and Ndebele. | Could | 4 |

**How requirements will be checked.** Before a phase starts, every Must requirement in that phase gets a written acceptance test: a clear pass or fail check. FR-20 passes when user code cannot reach any outside address in an automated test; FR-19 passes when the audit-log checker detects any edited or deleted entry. Phase exit criteria in section 12 are built from these tests.

## 7. Non-functional requirements (summary)

Privacy and compliance come first; where a setting differs between laws, the strictest one is the default everywhere.

| ID | Area | Requirement |
| --- | --- | --- |
| NFR-01 | Privacy | Customer data and model weights never leave the machine unless an admin has switched on a specific path. Every such transfer is logged. |
| NFR-02 | Privacy | No usage data (telemetry) is sent to us. |
| NFR-03 | Encryption | At rest and in transit (TLS 1.3 + mutual service checks). Customers hold their own keys. |
| NFR-04 | Audit | Logs are chained so any change or deletion shows up; exportable to the customer's SIEM; keep-time configurable. |
| NFR-05 | Isolation | User code is untrusted. Each session is sealed off from others and the host. |
| NFR-06 | Compliance | Controls support HIPAA, GDPR, SOC 2 and the ZW DPA. We say "supports", never "certified", until an independent audit confirms it, and every claim passes the legal review gate. |
| NFR-07 | Performance | A QLoRA fine-tune of a common open model must be practical on one 24–48 GB GPU. |
| NFR-08 | Scalability | Same software on 1 GPU, 8 GPUs, several servers, or an existing cluster, without changing screens or policies. |
| NFR-09 | Reliability | Full backup and restore; restore tested in every release. |
| NFR-10 | Usability | An SME admin with general IT skills can install and run it; analysts fine-tune through forms. |
| NFR-11 | Connectivity | Works fully on a local network/VPN; internet optional; fully offline possible with signed bundles. |
| NFR-12 | Supply-chain | Releases are signed; downloaded packages/models pass a scanning proxy. |
| NFR-13 | Maintainability | One codebase for all customers and internal use; settings versioned. |
| NFR-14 | Portability | Supported Linux + NVIDIA GPUs (section 20); other GPU makers to be assessed. |
| NFR-15 | Recovery | Single node: RTO under 4h, RPO under 1h. Multi-node targets defined in Phase 3. |
| NFR-16 | Observability | Metrics, logs and traces with configurable keep-time. |
| NFR-17 | Vulnerability mgmt | Critical CVEs in our software patched within 7 days of being known. |
| NFR-18 | Supply chain | Every release ships with an SBOM and build provenance. |
| NFR-19 | Accessibility | Screens meet WCAG 2.1 AA. |
| NFR-20 | Support | Response times per support tier; support available to offline customers. |
| NFR-21 | API | Versioned, rate-limited and documented. |
| NFR-22 | Durability | 99.9% data durability on a single node; higher with replication. |

## 8–15 (Business plan)

Sections 8–15 of the source proposal cover assumptions/constraints/risks, compliance and legal (with a legal review gate — no compliance claim ships until local counsel reviews it), commercial model (open core vs proprietary; per-install / per-GPU / per-user), go-to-market and pilot plan, the five-phase delivery plan (section 12, below), team and governance (~8 core engineers), open decisions (section 14, tracked as ADRs in this repo), and approval/next steps. They are retained in full in the original proposal; the repository tracks the decision-relevant parts in `docs/adr/` and `docs/decision-log.md`.

### 12. Delivery plan (phases)

| Phase | Focus | Estimate | Exit criteria |
| --- | --- | --- | --- |
| 0 | Single-node prototype | 6 weeks | Privacy model proven; no-egress test passed; audit hash chain verified |
| 1 | Pilot foundations | 8 weeks | SSO, registry, lineage, quotas, backup and restore working; pilot-ready |
| 2 | Model Studio | 8 weeks | Fine-tune templates, evaluation, model diff and policy packs working |
| 3 | Enterprise scale | 12 weeks | Online assist, signed updates, multi-node and per-dataset rules working |
| 4 | Market launch | 8 weeks | Plug-in kit, evidence exports, vendor SOC 2 in place |

### 14. Open decisions (tracked as ADRs)

Licensing model (open core vs proprietary) and pricing (per install / per GPU / per user) — before Phase 1 pilots. GPU vendors (NVIDIA only, or also AMD) — Phase 0. OS/driver support (Ubuntu 22.04/24.04 + CUDA 12+, RHEL 9 best effort) — Phase 0. First open models (Llama, Mistral, Qwen) — Phase 2. ZW DPA specifics — before any compliance claim. Vendor SOC 2 timing — Phase 3. Plug-in security — Phase 4.

# Part B — Technical Proposal

## 16. Solution overview and architecture

One set of services that runs the same way on one box or many. Only a small "runtime adapter" changes with the hardware, so screens, data and policies stay the same as a customer grows.

```
Browser UI / API / CLI
        | HTTPS, TLS 1.3
     Gateway / API  (SSO+MFA, RBAC, rate limiting, audit)
        |
   Control plane:
     - Session & kernel manager
     - Job queue & scheduler
     - Experiment tracker (MLflow API)
     - Model & dataset registry (versions, lineage, model cards)
     - Policy engine (policy-as-code: exports, egress, data use)   <-- choke point
     - Data governance service (labels, retention, DSAR)
     - Incident response service (alerts, breach reports)
        |
   Runtime adapter (start_kernel, run_job, allocate_gpu, stop, metrics)
        |                       Single-node first; Kubernetes, Slurm later
   Compute plane: sealed session containers (rootless, gVisor);
     GPUs whole / MIG / time-shared; NO outbound internet by default
   Storage plane: encrypted disks (customer keys), MinIO object store,
     package & model mirror, secrets store with key rotation
   Operations: backup w/ restore checks; Prometheus/Grafana/Loki; SIEM export
```

The key design rule: the control plane only talks to hardware through the runtime adapter's five commands. The single-machine adapter ships first; Kubernetes and Slurm adapters are added later without touching the screens or the policy layer.

## 17. Components and technology choices

Built on proven open-source parts and standard formats so customers keep their tools and are never locked in: web app over HTTPS; REST API (OpenAPI) + Python CLI; OIDC/SAML SSO + local accounts, RBAC, rate limiting; Jupyter kernel protocol + `.ipynb`; our own session/kernel manager; our own scheduler with quotas; MLflow-compatible tracker; our own registry on the object store; our own policy-as-code engine with packs; data governance service; incident response service; runtime adapter (single-node first); rootless Podman/Docker + gVisor isolation; GPU whole/MIG/time-share; encrypted disks + MinIO; local mirror with scanning proxy; local key service (pluggable to Vault); backup service; Prometheus/Grafana/Loki.

## 18. Privacy modes and compliance design

Data and models stay on the customer's machine unless an administrator opens a specific door, and every opened door is logged.

- **Standard (default):** nothing from user code leaves; the server may reach an approved mirror only; no telemetry.
- **Online-assisted (opt-in, per feature):** only what an admin switches on (vetted downloads via scanning proxy, signed updates, time-limited admin-started remote support, an AI coding helper that never sees datasets/weights and is blocked for personal/health-data projects unless an admin overrides).
- **Offline (air-gapped):** nothing leaves; updates/packages/models arrive as signed bundles.

The strictest common setting applies everywhere by default; policy packs (hipaa, gdpr, soc2, zw-dpa) tighten further; when two packs disagree, the stricter wins and the engine records the precedence. *This is an engineering mapping, not legal advice.*

## 19. Model editing features (Model Studio)

A guided loop: fine-tune (LoRA/QLoRA/full) → evaluate against the customer's own tests → model cards → licence & export checks → weight tools (merge/quantize/prune/inspect) → model diff → bias/fairness/red-team → visual pipeline view → export (safetensors/GGUF/ONNX to vLLM/TGI) → plug-in kit. Every step is recorded in the tracker and registry.

## 20. Hardware sizing and deployment profiles

| Profile | Customer | Hardware | Install | Recovery |
| --- | --- | --- | --- | --- |
| Single node (default) | SME | One workstation/server, 1–8 GPUs | Installer/appliance; Compose or system services; no K8s | RTO <4h, RPO <1h |
| Multi node | Mid/enterprise | Several GPU servers | Same services + K8s/Slurm adapter | Defined in Phase 3 |
| Existing cluster | Enterprise | Their K8s/Slurm | Control plane pointed at their scheduler | Agreed per customer |

Supported OS (proposed, confirmed Phase 0): Ubuntu 22.04 LTS (driver 535+, CUDA 12.2+, Full); Ubuntu 24.04 LTS (550+, 12.4+, Full); RHEL 9 (535+, 12.2+, Best effort).

Indicative single-box sizing: 24 GB → QLoRA of ~7–13B models + eval/shrink; 48 GB → QLoRA of ~30B (some 70B with care), LoRA of smaller; several 80 GB → full fine-tune of mid-size, faster runs, several users.

## 21. Security architecture

Assume user code is untrusted. Defences: sealed rootless containers + gVisor + least access (malicious code); gVisor + kernel hardening + pen tests (container escape); no-egress-by-default + policy-approved exports + transfer report (data exfiltration); signed releases + SBOM + provenance + scanning proxy (supply chain); SSO + MFA + timeouts + audit alerts (stolen credentials); encryption at rest with customer keys (lost disks). Security ops: CVE watch + 7-day critical patching (NFR-17); key rotation (FR-41); incident runbooks + breach workflow (FR-38); external pen test before Phase 3, then yearly.

## 22. Data governance

Every dataset is labelled on arrival (public/internal/personal/PHI, FR-33); that label controls who may use it, retention + scheduled deletion with a deletion record; DSAR via lineage search then export/erase + flag affected models (FR-45); ROPA export (FR-46); DPIA templates/workflow (FR-47).

## 23. Deployment and operations

Built to be run by a general IT admin: installer checks hardware and recommends models/methods; signed updates online or by offline bundle with one-step rollback; consistent snapshots with automatic test-restore; Prometheus/Grafana/Loki dashboards + SIEM export; support bundles with personal data removed (FR-40); remote help only when the admin opts in.

## 24. Extensibility and integration

REST API (OpenAPI, versioned, rate-limited, NFR-21); Python CLI; CI/CD via webhooks and GitOps; signed, sandboxed plug-ins for vision/speech/tabular model types.

*This document is an engineering and business plan, not legal advice. Confirm all compliance claims with qualified counsel.*
