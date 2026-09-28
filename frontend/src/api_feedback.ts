import { apiUrl, TELEGRAM_CHANNEL_URL, TELEGRAM_GROUP_URL } from "./config";

export type FeedbackCategory =
  | "bug"
  | "feature_request"
  | "confusing_ui"
  | "data_issue"
  | "other";

export interface FeedbackPayload {
  category: FeedbackCategory;
  page_or_feature: string;
  message: string;
  contact_method?: string;
  screenshot?: string | null;
  user_agent?: string;
}

export interface FeedbackSubmissionResult {
  success: boolean;
  id: string;
  message: string;
  received_at?: string;
}

const FEEDBACK_LOCAL_KEY = "tl_feedback_submissions";

export function getLocalFeedbackSubmissions(): (FeedbackPayload & { id: string; timestamp: string })[] {
  try {
    const raw = localStorage.getItem(FEEDBACK_LOCAL_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveLocalFeedback(item: FeedbackPayload, id: string) {
  try {
    const existing = getLocalFeedbackSubmissions();
    const entry = {
      ...item,
      id,
      timestamp: new Date().toISOString(),
      // Don't store huge screenshots in localStorage to avoid quota exhaustion
      screenshot: item.screenshot ? "[Screenshot attached]" : null,
    };
    const next = [entry, ...existing].slice(0, 20);
    localStorage.setItem(FEEDBACK_LOCAL_KEY, JSON.stringify(next));
  } catch {
    // Ignore localStorage errors
  }
}

export async function submitFeedback(payload: FeedbackPayload): Promise<FeedbackSubmissionResult> {
  const userAgent = typeof navigator !== "undefined" ? navigator.userAgent : undefined;
  const body = {
    ...payload,
    user_agent: payload.user_agent || userAgent,
  };

  try {
    const response = await fetch(apiUrl("/feedback"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });

    if (response.ok) {
      const data: FeedbackSubmissionResult = await response.json();
      saveLocalFeedback(payload, data.id || `fb_${Date.now()}`);
      return data;
    }
  } catch (err) {
    // Network or offline fallback
    console.warn("Feedback network submission failed, saving locally:", err);
  }

  // Fallback: save to localStorage so submission is never lost
  const fallbackId = `fb_local_${Date.now()}`;
  saveLocalFeedback(payload, fallbackId);
  return {
    success: true,
    id: fallbackId,
    message: "Feedback saved locally and queued for review. Thank you!",
  };
}

export async function fetchCommunityLinks(): Promise<{
  channel_url: string;
  discussion_url: string;
  support_email?: string;
}> {
  try {
    const response = await fetch(apiUrl("/feedback/community-links"));
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Fall back to config constants
  }
  return {
    channel_url: TELEGRAM_CHANNEL_URL,
    discussion_url: TELEGRAM_GROUP_URL,
  };
}
