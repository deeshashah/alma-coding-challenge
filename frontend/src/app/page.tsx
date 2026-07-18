import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { SESSION_COOKIE_NAME } from "@/lib/session";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Alma",
  description: "Immigration case intake and management.",
};

async function getHealth(): Promise<{ ok: boolean }> {
  try {
    const res = await fetch(`${process.env.API_URL}/api/health`, {
      cache: "no-store",
    });
    return { ok: res.ok };
  } catch {
    return { ok: false };
  }
}

export default async function Home() {
  const [health, sessionToken] = await Promise.all([
    getHealth(),
    cookies().then((store) => store.get(SESSION_COOKIE_NAME)?.value),
  ]);

  const attorneyHref = sessionToken ? "/dashboard" : "/login";
  const attorneyLabel = sessionToken ? "Go to dashboard" : "Log in";

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div className={styles.intro}>
          <h1>Immigration case management, simplified.</h1>
          <p>
            Prospective clients share their details once. Attorneys review, track, and follow up
            — all in one place.
          </p>
        </div>

        <div className={styles.cards}>
          <div className={styles.card}>
            <span className={styles.badge}>For applicants</span>
            <h2>Get started</h2>
            <p>Share your information and resume, and an attorney will follow up with you.</p>
            <Link href="/apply" className={`${styles.button} ${styles.primary}`}>
              Apply now
            </Link>
          </div>

          <div className={styles.card}>
            <span className={styles.badge}>For attorneys</span>
            <h2>Attorney portal</h2>
            <p>Review incoming leads, filter by status, and mark prospects as reached out.</p>
            <Link href={attorneyHref} className={`${styles.button} ${styles.secondary}`}>
              {attorneyLabel}
            </Link>
          </div>
        </div>
      </main>

      <div className={styles.status}>
        <span className={health.ok ? styles.statusDotUp : styles.statusDotDown} />
        API status: {health.ok ? "Operational" : "Unreachable"}
      </div>
    </div>
  );
}
