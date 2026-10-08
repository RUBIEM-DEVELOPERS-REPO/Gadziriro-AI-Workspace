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
}
