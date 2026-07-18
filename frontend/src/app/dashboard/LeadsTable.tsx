"use client";

import { Fragment, useOptimistic, useState, useTransition } from "react";
import { markReachedOut, type LeadOut } from "./actions";
import styles from "./dashboard.module.css";

type OptimisticUpdate = { id: string; state: "REACHED_OUT" };

function formatDate(iso: string): string {
  /** Render an ISO timestamp in the viewer's locale; callers keep the raw
   * ISO string available via a `title` attribute for precision. */
  return new Date(iso).toLocaleString();
}

export default function LeadsTable({ leads }: { leads: LeadOut[] }) {
  /** Render the leads table with an optimistic "Mark as Reached Out" action
   * per row: the row's displayed state flips immediately on click, then
   * reconciles with server truth once the Server Action resolves (and
   * revalidation refetches the list). */
  const [optimisticLeads, applyOptimisticUpdate] = useOptimistic(
    leads,
    (state, update: OptimisticUpdate) =>
      state.map((lead) => (lead.id === update.id ? { ...lead, state: update.state } : lead)),
  );
  const [isPending, startTransition] = useTransition();
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  function handleMarkReachedOut(id: string) {
    setRowErrors((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });

    startTransition(async () => {
      applyOptimisticUpdate({ id, state: "REACHED_OUT" });
      const result = await markReachedOut(id);
      if (!result.ok) {
        setRowErrors((prev) => ({ ...prev, [id]: result.error }));
      }
    });
  }

  if (optimisticLeads.length === 0) {
    return <p className={styles.empty}>No leads found.</p>;
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>First Name</th>
            <th>Last Name</th>
            <th>Email</th>
            <th>Resume</th>
            <th>State</th>
            <th>Created At</th>
            <th>Updated At</th>
            <th className={styles.actionsCell}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {optimisticLeads.map((lead) => (
            <Fragment key={lead.id}>
              <tr>
                <td className={styles.idCell} title={lead.id}>
                  {lead.id}
                </td>
                <td>{lead.firstName}</td>
                <td>{lead.lastName}</td>
                <td>{lead.email}</td>
                <td>
                  <a href={lead.resumeUrl} target="_blank" rel="noreferrer">
                    View
                  </a>
                </td>
                <td>
                  <span
                    className={
                      lead.state === "PENDING" ? styles.statePending : styles.stateReachedOut
                    }
                  >
                    {lead.state === "PENDING" ? "Pending" : "Reached Out"}
                  </span>
                </td>
                <td title={lead.createdAt}>{formatDate(lead.createdAt)}</td>
                <td title={lead.updatedAt}>{formatDate(lead.updatedAt)}</td>
                <td className={styles.actionsCell}>
                  {lead.state === "PENDING" ? (
                    <button
                      type="button"
                      className={styles.actionButton}
                      disabled={isPending}
                      onClick={() => handleMarkReachedOut(lead.id)}
                    >
                      Mark as Reached Out
                    </button>
                  ) : (
                    <span className={styles.textSecondary}>—</span>
                  )}
                </td>
              </tr>
              {rowErrors[lead.id] && (
                <tr>
                  <td colSpan={9} className={styles.rowError}>
                    {rowErrors[lead.id]}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
