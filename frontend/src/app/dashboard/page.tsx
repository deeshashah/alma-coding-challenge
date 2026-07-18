import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect, unstable_rethrow } from "next/navigation";
import { SESSION_COOKIE_NAME } from "@/lib/session";
import StateFilter from "./StateFilter";
import LeadsTable from "./LeadsTable";
import type { LeadOut } from "./actions";
import styles from "./dashboard.module.css";

export const metadata: Metadata = {
  title: "Leads",
};

type LeadState = "PENDING" | "REACHED_OUT";

const VALID_STATES: LeadState[] = ["PENDING", "REACHED_OUT"];

function parseState(raw: string | undefined): LeadState | undefined {
  /** Only accept the two known state values; anything else means "show all". */
  return VALID_STATES.find((state) => state === raw);
}

type LeadListResponse = {
  items: LeadOut[];
  page: number;
  pageSize: number;
  total: number;
};

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string }>;
}) {
  /** Render the leads dashboard: fetch the current page of leads from the
   * backend (optionally filtered by state) and render the filter + table. */
  const { state: rawState } = await searchParams;
  const state = parseState(rawState);

  const token = (await cookies()).get(SESSION_COOKIE_NAME)?.value;
  if (!token) {
    redirect("/login");
  }

  const apiUrl = process.env.API_URL;
  const params = new URLSearchParams();
  if (state) params.set("state", state);
  const query = params.toString();

  let data: LeadListResponse | null = null;
  let loadError = false;

  if (!apiUrl) {
    loadError = true;
  } else {
    try {
      const response = await fetch(`${apiUrl}/api/leads${query ? `?${query}` : ""}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });

      if (response.status === 401) {
        redirect("/login");
      } else if (response.ok) {
        data = (await response.json()) as LeadListResponse;
      } else {
        loadError = true;
      }
    } catch (err) {
      unstable_rethrow(err);
      loadError = true;
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Leads</h1>
          <StateFilter currentState={state} />
        </div>

        {loadError && <p className={styles.error}>Couldn&apos;t load leads.</p>}
        {!loadError && data && <LeadsTable leads={data.items} />}
      </main>
    </div>
  );
}
