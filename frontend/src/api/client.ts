// Typed fetch client for the Gadziriro gateway REST API.
// All requests include credentials so the httponly session cookie is sent.

export interface PrincipalOut {
  user_id: string
  username: string
  roles: string[]
}

export interface SessionOut {
  session_id: string
  kernel_id: string
  status: string
  gpu_ids: number[]
  allow_egress: boolean
}

export interface HardwareReport {
  gpu_present: boolean
  gpu_count: number
  gpu_memory_mb: number[]
  cpu_count: number
  ram_mb: number
  disk_free_gb: number
  supported_methods: string[]
  recommended_model_sizes: string[]
  warnings: string[]
}

export interface AuditVerifyOut {
  ok: boolean
  count: number
  broken_at?: number
  detail: string
}

export interface RunCellOut {
  output: string
  [key: string]: unknown
}

// --- Phase 1 contracts -----------------------------------------------------

export interface DatasetVersion {
  name: string
  version: string
  sensitivity: string
  source: string
  subjects: string[]
  created_at: string
}

export interface ModelLineage {
  dataset_refs: string[]
  code_ref: string
  params: Record<string, unknown>
  hardware: string
  run_id: string
}

export interface ModelVersion {
  name: string
  version: string
  flagged: boolean
  sensitivity: string
  created_at: string
  lineage: ModelLineage
}

export interface Job {
  job_id: string
  user: string
  project: string
  status: string
  submitted_at: string
}

export interface Backup {
  id: string
  created_at?: string
  status?: string
  size_bytes?: number
}

export interface ExportRequest {
  id: string
  status: string
  resource_ref?: string
  sensitivity?: string
  requested_by?: string
  created_at?: string
}

export interface MfaEnrollOut {
  secret: string
  provisioning_uri: string
}

// --- Phase 2 contracts: Model Studio, Evaluation, Weights, Compliance ------

export interface FinetuneRequest {
  base_model: string
  method: string
  dataset_refs: string[]
  output_name: string
  hyperparams?: Record<string, unknown>
}

export interface TrainingResult {
  model_ref: string
  run_id: string
  method: string
  base_model: string
  metrics: Record<string, unknown>
}

export interface ModelExportResult {
  model_ref: string
  format: string
  serving_manifest: Record<string, unknown>
  serving_command?: string[]
}

export interface EvalSample {
  prompt: string
  expected: string
  weight?: number
}

export interface EvalResult {
  model_ref: string
  suite: EvalSample[]
  score: number
  samples?: unknown[]
}

export interface ComparisonResult {
  a_ref: string
  b_ref: string
  score_a: number
  score_b: number
  score_delta: number
  sample_diffs?: unknown[]
}

// Weight tooling results are open-shaped; the view renders defensively.
export interface WeightToolResult {
  model_ref?: string
  summary?: unknown
  [key: string]: unknown
}

export interface PolicyPack {
  id?: string
  name?: string
  description?: string
  [key: string]: unknown
}

export interface EffectivePolicy {
  settings: Record<string, unknown>
  provenance: Record<string, unknown>
}

export interface LicenseCheckResult {
  ok: boolean
  reason?: string
  detail?: string
  [key: string]: unknown
}

export interface Incident {
  id: string
  title?: string
  severity?: string
  breach?: boolean
  status?: string
  created_at?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      // response had no JSON body; keep statusText
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) {
    return undefined as T
  }

  const text = await res.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

// Variant for endpoints that return plain text (e.g. Prometheus /metrics).
async function requestText(path: string, init?: RequestInit): Promise<string> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
  })
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText)
  }
  return res.text()
}

export const api = {
  // Auth
  login(username: string, password: string): Promise<PrincipalOut> {
    return request<PrincipalOut>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  logout(): Promise<void> {
    return request<void>('/api/auth/logout', { method: 'POST' })
  },

  me(): Promise<PrincipalOut> {
    return request<PrincipalOut>('/api/auth/me')
  },

  // Sessions
  listSessions(): Promise<SessionOut[]> {
    return request<SessionOut[]>('/api/sessions')
  },

  createSession(sessionId: string, gpuMemoryMb?: number): Promise<SessionOut> {
    const body: { session_id: string; gpu_memory_mb?: number } = {
      session_id: sessionId,
    }
    if (gpuMemoryMb !== undefined) body.gpu_memory_mb = gpuMemoryMb
    return request<SessionOut>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  stopSession(id: string): Promise<void> {
    return request<void>(`/api/sessions/${encodeURIComponent(id)}/stop`, {
      method: 'POST',
    })
  },

  runCell(id: string, code: string): Promise<RunCellOut> {
    return request<RunCellOut>(
      `/api/sessions/${encodeURIComponent(id)}/run-cell`,
      {
        method: 'POST',
        body: JSON.stringify({ code }),
      },
    )
  },

  // Installer
  hardware(): Promise<HardwareReport> {
    return request<HardwareReport>('/api/installer/hardware')
  },

  // Audit
  auditVerify(): Promise<AuditVerifyOut> {
    return request<AuditVerifyOut>('/api/audit/verify')
  },

  // Registry — datasets & models (FR-06/07/08)
  listDatasets(): Promise<DatasetVersion[]> {
    return request<DatasetVersion[]>('/api/datasets')
  },

  listModels(): Promise<ModelVersion[]> {
    return request<ModelVersion[]>('/api/models')
  },

  getModel(name: string, version: string): Promise<ModelVersion> {
    return request<ModelVersion>(
      `/api/models/${encodeURIComponent(name)}/${encodeURIComponent(version)}`,
    )
  },

  // Jobs (FR-05)
  listJobs(): Promise<Job[]> {
    return request<Job[]>('/api/jobs')
  },

  submitJob(
    command: string[],
    project: string,
    gpuMemoryMb?: number,
  ): Promise<Job> {
    const body: { command: string[]; project: string; gpu_memory_mb?: number } = {
      command,
      project,
    }
    if (gpuMemoryMb !== undefined) body.gpu_memory_mb = gpuMemoryMb
    return request<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // Metrics (Prometheus text exposition)
  metrics(): Promise<string> {
    return requestText('/metrics')
  },

  // Backups / disaster recovery (FR-28/39)
  listBackups(): Promise<Backup[]> {
    return request<Backup[]>('/api/backups')
  },

  createBackup(): Promise<Backup> {
    return request<Backup>('/api/backups', { method: 'POST' })
  },

  testRestore(id: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(
      `/api/backups/${encodeURIComponent(id)}/test-restore`,
      { method: 'POST' },
    )
  },

  // Governance — retention, DSAR, erasure (FR-22/23)
  retentionRun(
    policies: { dataset_name: string; retain_days?: number }[] = [],
  ): Promise<{ deleted: number; proofs: unknown[] }> {
    return request<{ deleted: number; proofs: unknown[] }>(
      '/api/governance/retention/run',
      { method: 'POST', body: JSON.stringify({ policies }) },
    )
  },

  dsar(subject: string): Promise<ModelVersion[]> {
    return request<ModelVersion[]>(
      `/api/governance/dsar/${encodeURIComponent(subject)}`,
    )
  },

  dsarErase(subject: string): Promise<{ flagged: string[] }> {
    return request<{ flagged: string[] }>(
      `/api/governance/dsar/${encodeURIComponent(subject)}/erase`,
      { method: 'POST' },
    )
  },

  // Exports — request / review (FR-21)
  listExports(): Promise<ExportRequest[]> {
    return request<ExportRequest[]>('/api/exports')
  },

  requestExport(resourceRef: string, sensitivity: string): Promise<ExportRequest> {
    return request<ExportRequest>('/api/exports', {
      method: 'POST',
      body: JSON.stringify({ resource_ref: resourceRef, sensitivity }),
    })
  },

  approveExport(id: string): Promise<void> {
    return request<void>(`/api/exports/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
    })
  },

  denyExport(id: string): Promise<void> {
    return request<void>(`/api/exports/${encodeURIComponent(id)}/deny`, {
      method: 'POST',
    })
  },

  // MFA enrolment
  mfaEnroll(): Promise<MfaEnrollOut> {
    return request<MfaEnrollOut>('/api/mfa/enroll', { method: 'POST' })
  },

  mfaVerify(code: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>('/api/mfa/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
    })
  },

  // --- Model Studio (FR-10/15) ---------------------------------------------
  finetune(body: FinetuneRequest): Promise<TrainingResult> {
    return request<TrainingResult>('/api/modelstudio/finetune', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  modelExport(modelRef: string, format: string): Promise<ModelExportResult> {
    return request<ModelExportResult>('/api/modelstudio/export', {
      method: 'POST',
      body: JSON.stringify({ model_ref: modelRef, format }),
    })
  },

  modelStudioTemplates(): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('/api/modelstudio/templates')
  },

  // --- Evaluation (FR-11/13) -----------------------------------------------
  evalRun(
    modelRef: string,
    suite: EvalSample[],
    suiteName?: string,
  ): Promise<EvalResult> {
    const body: {
      model_ref: string
      suite: EvalSample[]
      suite_name?: string
    } = { model_ref: modelRef, suite }
    if (suiteName) body.suite_name = suiteName
    return request<EvalResult>('/api/evaluation/run', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  evalCompare(
    aRef: string,
    bRef: string,
    suite: EvalSample[],
  ): Promise<ComparisonResult> {
    return request<ComparisonResult>('/api/evaluation/compare', {
      method: 'POST',
      body: JSON.stringify({ a_ref: aRef, b_ref: bRef, suite }),
    })
  },

  evalDiff(
    aRef: string,
    bRef: string,
    suite?: EvalSample[],
  ): Promise<ComparisonResult> {
    const body: { a_ref: string; b_ref: string; suite?: EvalSample[] } = {
      a_ref: aRef,
      b_ref: bRef,
    }
    if (suite) body.suite = suite
    return request<ComparisonResult>('/api/evaluation/diff', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // --- Weight tooling (FR-12) ----------------------------------------------
  weightMerge(body: Record<string, unknown>): Promise<WeightToolResult> {
    return request<WeightToolResult>('/api/weighttools/merge', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  weightQuantize(body: Record<string, unknown>): Promise<WeightToolResult> {
    return request<WeightToolResult>('/api/weighttools/quantize', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  weightPrune(body: Record<string, unknown>): Promise<WeightToolResult> {
    return request<WeightToolResult>('/api/weighttools/prune', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  weightInspect(name: string, version: string): Promise<WeightToolResult> {
    return request<WeightToolResult>(
      `/api/weighttools/inspect/${encodeURIComponent(name)}/${encodeURIComponent(
        version,
      )}`,
    )
  },

  // --- Model cards (FR-36) — may return {markdown} JSON or raw markdown -----
  modelCard(name: string, version: string): Promise<string> {
    return requestText(
      `/api/modelcards/${encodeURIComponent(name)}/${encodeURIComponent(version)}`,
    )
  },

  // --- Licensing (FR-48) ---------------------------------------------------
  licensing(model: string): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>(
      `/api/licensing/${encodeURIComponent(model)}`,
    )
  },

  licensingCheck(
    model: string,
    intendedUse: string,
    destination?: string,
  ): Promise<LicenseCheckResult> {
    const body: {
      model: string
      intended_use: string
      destination?: string
    } = { model, intended_use: intendedUse }
    if (destination) body.destination = destination
    return request<LicenseCheckResult>('/api/licensing/check', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // --- Policy packs (FR-24) ------------------------------------------------
  policyPacks(): Promise<PolicyPack[]> {
    return request<PolicyPack[]>('/api/policy/packs')
  },

  policyEffective(enabled: string[]): Promise<EffectivePolicy> {
    return request<EffectivePolicy>('/api/policy/packs/effective', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    })
  },

  // --- Incident response (FR-38) -------------------------------------------
  createIncident(
    title: string,
    severity: string,
    breach?: boolean,
  ): Promise<Incident> {
    const body: { title: string; severity: string; breach?: boolean } = {
      title,
      severity,
    }
    if (breach !== undefined) body.breach = breach
    return request<Incident>('/api/incidents', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  listIncidents(): Promise<Incident[]> {
    return request<Incident[]>('/api/incidents')
  },

  incidentBreachReport(id: string): Promise<string> {
    return requestText(
      `/api/incidents/${encodeURIComponent(id)}/breach-report`,
    )
  },

  // --- DSAR direct (FR-45) -------------------------------------------------
  dsarSubjectExport(subject: string): Promise<unknown> {
    return request<unknown>(
      `/api/dsar/${encodeURIComponent(subject)}/export`,
      { method: 'POST' },
    )
  },

  dsarSubjectErase(subject: string): Promise<unknown> {
    return request<unknown>(
      `/api/dsar/${encodeURIComponent(subject)}/erase`,
      { method: 'POST' },
    )
  },

  // --- Support bundle (FR-40) ----------------------------------------------
  supportBundle(): Promise<unknown> {
    return request<unknown>('/api/support/bundle', { method: 'POST' })
  },
}
