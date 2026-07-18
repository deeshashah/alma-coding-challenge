import type { Metadata } from "next";
import ApplyForm from "./ApplyForm";
import styles from "./apply.module.css";

export const metadata: Metadata = {
  title: "Apply",
};

export default function ApplyPage() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <ApplyForm />
      </main>
    </div>
  );
}
