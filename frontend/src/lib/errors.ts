import { ApiError } from "../api/client";

const MESSAGES: Record<string, string> = {
  network_error: "We couldn't reach the review service. Check that the API is running, then try again.",
  llm_rate_limited: "The AI provider is temporarily rate limited. Try again shortly.",
  llm_timeout: "The AI provider took too long to respond. Try again.",
  llm_auth_failed: "The AI provider rejected the configured credentials.",
  llm_invalid_output: "The AI returned a response we couldn't use. Try again.",
  llm_provider_error: "The AI provider couldn't process the request. Try again.",
  metadata_providers_unavailable:
    "Paper metadata services are unavailable right now. Try again shortly.",
  analysis_in_progress: "This draft is already being analyzed.",
  draft_too_large: "The draft is longer than the 20,000-character limit.",
  draft_empty: "Paste some text to analyze.",
  not_found: "This review could not be found.",
  database_unavailable: "The review service is temporarily unavailable. Try again shortly.",
};

const FALLBACK = "Something went wrong on our side. Try again.";

export interface UserFacingError {
  message: string;
  /** Shown in small text so a failure can be traced in server logs. */
  requestId: string | null;
  retryable: boolean;
}

export function toUserError(error: unknown): UserFacingError {
  if (error instanceof ApiError) {
    const validation = error.code === "validation_error" ? error.details[0]?.msg : undefined;
    return {
      message: MESSAGES[error.code] ?? validation ?? FALLBACK,
      requestId: error.requestId,
      retryable: !["draft_too_large", "draft_empty", "not_found", "llm_auth_failed"].includes(error.code),
    };
  }
  return { message: FALLBACK, requestId: null, retryable: true };
}
