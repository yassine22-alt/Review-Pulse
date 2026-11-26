import type { ReactNode } from "react";

export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" />
      <path d="M5 17h6l3-8 4 15 3-7h6" />
    </svg>
  );
}

export const Spinner = ({ label }: { label: string }) => (
  <div className="spinner" role="status"><i aria-hidden="true" />{label}</div>
);

export const Problem = ({ text }: { text: string }) => (text ? <p className="problem" role="alert">{text}</p> : null);

export const Field = ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
  <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
);

export const when = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
