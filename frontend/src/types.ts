export interface Usage {
  total: number
  used: number
  percent: number
}

export interface SystemSnapshot {
  cpu_percent: number
  cpu_per_core: number[]
  memory: Usage
  swap: Usage
  disks: Array<Usage & { path: string }>
  network: { bytes_sent: number; bytes_received: number }
  load_average: number[]
  uptime_seconds: number
  operating_system: string
  kernel_version: string
}

export interface Service {
  name: string
  active: boolean
  status: string
}

export interface AppManifest {
  name: string
  display_name: string
  description: string
  category: string
  installed: boolean
  status: string
  ports: number[]
  service?: { name?: string }
}

export interface Container {
  id: string
  name: string
  image: string
  status: string
  cpu_percent?: string
  memory_percent?: string
  memory_usage?: string
}

export interface Project {
  id: number
  name: string
  code: string
  project_type: string
  repository: string
  branch: string
  deploy_path: string
}

export interface Alert {
  type: string
  severity: string
  resource: string
  value: number
  message: string
}

export interface Backup {
  name: string
  filename: string
  path: string
  size: number
  created_at: string
}
