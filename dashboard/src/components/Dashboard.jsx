"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import StepTripleLock from "./StepTripleLock";
import { StepAnother, StepCentral } from "./StepPath";
import StepPensioner from "./StepPensioner";
import StepPopulation from "./StepPopulation";
import SummaryTab from "./SummaryTab";
import MethodTab from "./MethodTab";
import SampleBanner from "./SampleBanner";
import { fyLabel, getHorizon, getRunsWithTables } from "../lib/dataHelpers";
import { readTrajectories } from "../lib/trajectoryHelpers";
import { trajectoryLabels } from "./PathCharts";
import { ReplicationLine } from "./Benchmarks";

export const TAB_OPTIONS = [
  { id: "triple-lock", label: "1. The triple lock" },
  { id: "central", label: "2. The OBR's forecast" },
  { id: "path", label: "3. Another path" },
  { id: "pensioner", label: "4. One pensioner" },
  { id: "everyone", label: "5. Everyone" },
  { id: "cost", label: "6. Every path" },
  { id: "method", label: "Method" },
];
export const DEFAULT_TAB = "triple-lock";

function getInitialTab(tabParam) {
  if (TAB_OPTIONS.some((tab) => tab.id === tabParam)) {
    return tabParam;
  }
  return DEFAULT_TAB;
}

export function Dashboard({ data }) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState(() => getInitialTab(searchParams.get("tab")));
  const [pathId, setPathId] = useState("random");
  const { trajectories } = readTrajectories(data);
  const records = getRunsWithTables(data);
  const labels = trajectoryLabels(data);
  const horizon = getHorizon(data);
  const period = horizon
    ? `${fyLabel(horizon[0])} to ${fyLabel(horizon[horizon.length - 1])}`
    : null;

  useEffect(() => {
    setActiveTab(getInitialTab(searchParams.get("tab")));
  }, [searchParams]);

  function handleTabChange(tab) {
    setActiveTab(tab);
    if (tab === DEFAULT_TAB) {
      router.replace("/", { scroll: false });
      return;
    }
    router.replace(`/?tab=${tab}`, { scroll: false });
  }

  return (
    <div className="app-shell min-h-screen">
      <header className="title-row">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4 md:px-8">
          <h1>The State Pension triple lock</h1>
        </div>
      </header>

      <main className="relative z-[1] mx-auto max-w-[1400px] px-6 py-10 md:px-8 md:py-12">
        <SampleBanner data={data} />
        <div className="animate-[fadeIn_0.4s_ease-out]">
          <p className="mb-3 text-[1.05rem] leading-relaxed text-slate-600">
            The triple lock raises the State Pension each April by the highest of CPI inflation,
            earnings growth or 2.5%. On 29 September 2026 Prime Minister Andy Burnham{" "}
            <a
              href="https://www.bbc.co.uk/news/live/c6x2zrv774gvt?post=asset%3A7a078b64-1a5e-4ab2-995f-6afcb5daae5d#post"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              said
            </a>{" "}
            he would keep the triple lock until 2030 and then &quot;adjust&quot; it: the pension would rise
            every year with prices or 2.5%, and &quot;it will hold its value relative to earnings over
            time&quot;. DWP describes it as a rise of at least inflation or 2.5%, plus whatever
            keeps the pension at its record value relative to earnings; we read inflation as CPI and that record as the
            2029-30 level. We use{" "}
            <a href="https://policyengine.org/uk" target="_blank" rel="noreferrer" className="underline">
              PolicyEngine UK
            </a>{" "}
            to compare it with the triple lock{period ? `, ${period}` : ""}. Every fiscal and household figure
            is a full model run. The steps build up: how the triple lock works; the OBR&apos;s central forecast; another
            possible path; what that path means for one pensioner and for everyone; and the saving to
            expect across every path.
          </p>
        </div>

        <div
          className="mb-8 mt-8 flex w-fit flex-wrap border-b-2 border-slate-200"
          role="tablist"
          aria-label="Dashboard sections"
        >
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => handleTabChange(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "triple-lock" && <StepTripleLock data={data} />}
        {activeTab === "central" && <StepCentral data={data} trajectories={trajectories} labels={labels} />}
        {activeTab === "path" && (
          <StepAnother data={data} trajectories={trajectories} labels={labels} pathId={pathId} onPath={setPathId} />
        )}
        {activeTab === "pensioner" && (
          <StepPensioner data={data} records={records} labels={labels} pathId={pathId} onPath={setPathId} />
        )}
        {activeTab === "everyone" && (
          <StepPopulation data={data} records={records} trajectories={trajectories} labels={labels} pathId={pathId} onPath={setPathId} />
        )}
        {activeTab === "cost" && <SummaryTab data={data} />}
        {activeTab === "method" && <MethodTab data={data} />}

        <footer className="mt-12 border-t border-slate-200 pt-8 text-center text-sm text-slate-500">
          <ReplicationLine data={data} />
        </footer>
      </main>
    </div>
  );
}

export default Dashboard;
