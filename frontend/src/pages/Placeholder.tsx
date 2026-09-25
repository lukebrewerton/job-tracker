// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useParams } from "react-router";

/** A page whose content arrives in a later ticket. */
function Placeholder({ title, ticket }: { title: string; ticket: string }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-slate-600">Coming soon ({ticket}).</p>
    </section>
  );
}

export const Dashboard = () => <Placeholder title="Dashboard" ticket="JT-36" />;
export const Jobs = () => <Placeholder title="Jobs" ticket="JT-31" />;
export const NewJob = () => <Placeholder title="New job" ticket="JT-32" />;
export const Interviews = () => (
  <Placeholder title="Interviews" ticket="JT-35" />
);

export function JobDetail() {
  const { id } = useParams();
  return <Placeholder title={`Job ${id ?? ""}`} ticket="JT-33" />;
}
