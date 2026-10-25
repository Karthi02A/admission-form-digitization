export function apiBase(): string {
  if (typeof window !== "undefined") {
    const override = new URLSearchParams(window.location.search).get("api");
    if (override) return override.replace(/\/+$/, "");
  }
  return (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = JSON.parse(await response.text()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      detail = `Request failed (${response.status})`;
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
