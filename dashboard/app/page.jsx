"use client";

import Dashboard from "../src/components/Dashboard";
import results from "../public/data/results.json";

// Dashboard holds its own Suspense boundary around the tabs, the one part that reads the address's ?tab=.
export default function Page() {
  return <Dashboard data={results} />;
}
