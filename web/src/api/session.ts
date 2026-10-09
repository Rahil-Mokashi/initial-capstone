// The session token lives in memory only - never localStorage - so closing the
// app always signs the user out. One listener lets the API client tell the app
// the session ended (expired, or logged out elsewhere).
let token: string | null = null;
let onSessionLost: (() => void) | null = null;

export const session = {
  get token() {
    return token;
  },
  set(value: string | null) {
    token = value;
  },
  onLost(listener: (() => void) | null) {
    onSessionLost = listener;
  },
  lost() {
    token = null;
    onSessionLost?.();
  },
};
