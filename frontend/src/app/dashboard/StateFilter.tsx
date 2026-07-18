"use client";

import { useRouter, usePathname } from "next/navigation";
import styles from "./dashboard.module.css";

type LeadState = "PENDING" | "REACHED_OUT";

export default function StateFilter({ currentState }: { currentState?: LeadState }) {
  /** Dropdown that filters the leads table by state, reflected in the URL's
   * `?state=` query param so the filter survives a refresh and is applied
   * server-side by page.tsx. */
  const router = useRouter();
  const pathname = usePathname();

  function handleChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === "ALL") {
      router.push(pathname);
    } else {
      router.push(`${pathname}?state=${value}`);
    }
  }

  return (
    <select
      className={styles.filter}
      value={currentState ?? "ALL"}
      onChange={handleChange}
      aria-label="Filter leads by state"
    >
      <option value="ALL">All</option>
      <option value="PENDING">Pending</option>
      <option value="REACHED_OUT">Reached Out</option>
    </select>
  );
}
