import { apiUrl } from "@/lib/api";

const VISITOR_STORAGE_KEY = "admission_analytics_visitor_v1";
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
const HEARTBEAT_INTERVAL_MS = 30 * 1000;

type StoredSession = {
  visitorId: string;
  sessionId: string;
  lastActivityAt: number;
};

type AnalyticsIdentity = {
  visitor_id: string;
  session_id: string;
};

function createId(): string {
  return window.crypto.randomUUID();
}

function getVisitorId(): string {
  try {
    const existing = window.localStorage.getItem(VISITOR_STORAGE_KEY);
    if (existing) return existing;
    const created = createId();
    window.localStorage.setItem(VISITOR_STORAGE_KEY, created);
    return created;
  } catch {
    // Tracking remains best-effort if browser storage is unavailable.
    return createId();
  }
}

// Keep one session identity for this loaded page. This prevents React
// Strict Mode's development-only effect cleanup/setup cycle from creating
// duplicate visits. A full page reload creates a fresh module context,
// so the next page load receives a new session ID.
let pageSession: StoredSession | null = null;

function getSession(visitorId: string): { session: StoredSession; created: boolean } {
  const now = Date.now();

  if (
    pageSession &&
    pageSession.visitorId === visitorId &&
    pageSession.sessionId &&
    Number.isFinite(pageSession.lastActivityAt) &&
    now - pageSession.lastActivityAt <= SESSION_TIMEOUT_MS
  ) {
    return { session: pageSession, created: false };
  }

  const session: StoredSession = {
    visitorId,
    sessionId: createId(),
    lastActivityAt: now,
  };

  pageSession = session;
  return { session, created: true };
}

// Used by the upload workflow so document events can be attributed to the
// same anonymous browser and page visit as the existing session tracker.
export function getAnalyticsIdentity(): AnalyticsIdentity {
  if (typeof window === "undefined") {
    return { visitor_id: "", session_id: "" };
  }

  const visitorId = getVisitorId();
  const { session } = getSession(visitorId);
  return {
    visitor_id: visitorId,
    session_id: session.sessionId,
  };
}

async function postAnalytics(path: string, body: object, keepalive = false): Promise<void> {
  try {
    await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive,
      credentials: "omit",
    });
  } catch {
    // Analytics must never interrupt uploads, extraction, review or export.
  }
}

export function startUsageTracking(): () => void {
  if (typeof window === "undefined") return () => undefined;

  const visitorId = getVisitorId();
  let { session } = getSession(visitorId);
  let lastTickAt = Date.now();
  let isActive = document.visibilityState === "visible" && document.hasFocus();

  const identity = (): AnalyticsIdentity => ({
    visitor_id: visitorId,
    session_id: session.sessionId,
  });

  const startSession = () => {
    void postAnalytics("/api/analytics/session/start", identity());
  };

  const refreshSessionIfNeeded = () => {
    const next = getSession(visitorId);
    session = next.session;
    if (next.created) startSession();
    lastTickAt = Date.now();
  };

  const sendHeartbeat = (keepalive = false) => {
    const now = Date.now();
    const elapsedSeconds = Math.min(60, Math.max(0, Math.floor((now - lastTickAt) / 1000)));
    lastTickAt = now;
    if (elapsedSeconds <= 0) return;

    session.lastActivityAt = now;

    void postAnalytics(
      "/api/analytics/session/heartbeat",
      { ...identity(), active_seconds: elapsedSeconds },
      keepalive,
    );
  };

  // Idempotently register/resume the browser session on each app visit.
  startSession();

  const syncActiveState = () => {
    const nextIsActive = document.visibilityState === "visible" && document.hasFocus();
    if (isActive && !nextIsActive) sendHeartbeat(true);
    if (!isActive && nextIsActive) refreshSessionIfNeeded();
    isActive = nextIsActive;
  };

  const interval = window.setInterval(() => {
    if (isActive && document.visibilityState === "visible" && document.hasFocus()) {
      sendHeartbeat();
    } else {
      syncActiveState();
    }
  }, HEARTBEAT_INTERVAL_MS);

  const handlePageHide = () => {
    if (isActive) sendHeartbeat(true);
    isActive = false;
  };

  document.addEventListener("visibilitychange", syncActiveState);
  window.addEventListener("focus", syncActiveState);
  window.addEventListener("blur", syncActiveState);
  window.addEventListener("pagehide", handlePageHide);

  return () => {
    window.clearInterval(interval);
    if (isActive) sendHeartbeat(true);
    document.removeEventListener("visibilitychange", syncActiveState);
    window.removeEventListener("focus", syncActiveState);
    window.removeEventListener("blur", syncActiveState);
    window.removeEventListener("pagehide", handlePageHide);
  };
}
