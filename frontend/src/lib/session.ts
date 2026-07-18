// Shared session cookie contract between the login action, dashboard, and
// middleware. Deliberately dependency-free so it can be imported from both
// the Node runtime (Server Actions/Components) and the Edge runtime
// (middleware.ts).

export const SESSION_COOKIE_NAME = "session_token";

// Matches the backend's default JWT_EXPIRE_MINUTES (auth_service.py); the
// cookie shouldn't outlive the token it holds.
export const SESSION_MAX_AGE_SECONDS = 60 * 60;
