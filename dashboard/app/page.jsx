"use client";

import { Suspense } from "react";
import Dashboard from "../src/components/Dashboard";
import results from "../public/data/triple_lock_results.json";
import trajectories from "../public/data/trajectory_results.json";

export default function Page() {
  return (
    <Suspense fallback={<p className="p-12 text-center text-slate-500">Loading...</p>}>
      <Dashboard data={results} trajectories={trajectories} />
    </Suspense>
  );
}
