import type { Metadata } from "next";
import LoginForm from "./LoginForm";
import { sanitizeRedirectTo } from "./helpers";
import styles from "./login.module.css";

export const metadata: Metadata = {
  title: "Log in",
};

/** Server Component for /login: reads the `from` redirect target (set by
 * middleware.ts when redirecting an unauthenticated /dashboard visit),
 * sanitized against open redirects, and renders the client login form. */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const { from } = await searchParams;
  const redirectTo = sanitizeRedirectTo(from);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <LoginForm redirectTo={redirectTo} />
      </main>
    </div>
  );
}
