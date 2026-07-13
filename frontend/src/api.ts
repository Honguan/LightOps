export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = window.sessionStorage.getItem('lightops-token')
  const response = await fetch(`/api/${path}`, {
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...options,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail ?? '操作失敗')
  }
  return response.json() as Promise<T>
}

export const post = <T>(path: string, payload?: unknown) =>
  request<T>(path, { method: 'POST', body: payload === undefined ? undefined : JSON.stringify(payload) })

export function setSessionToken(token: string) {
  window.sessionStorage.setItem('lightops-token', token)
}
