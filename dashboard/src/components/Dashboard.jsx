"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import CostTab from "./CostTab";
import AffectedTab from "./AffectedTab";
import UncertaintyTab from "./UncertaintyTab";
import MethodologyTab from "./MethodologyTab";
import SampleBanner from "./SampleBanner";
import { describeBreakdowns, fyLabel, getHorizon } from "../lib/dataHelpers";
import { ReplicationLine } from "./Benchmarks";

export const TAB_OPTIONS = [
  { id: "cost", label: "Cost" },
  { id: "affected", label: "Who's affected" },
  { id: "uncertainty", label: "Uncertainty" },
  { id: "methodology", label: "Methodology" },
];

function getInitialTab(tabParam) {
  if (TAB_OPTIONS.some((tab) => tab.id === tabParam)) {
    return tabParam;
  }
  return "cost";
}

export function Dashboard({ data }) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState(() => getInitialTab(searchParams.get("tab")));
  const horizon = getHorizon(data);
  const groups = describeBreakdowns(data);
  const period = horizon
    ? `${fyLabel(horizon[0])} to ${fyLabel(horizon[horizon.length - 1])}`
    : null;

  useEffect(() => {
    setActiveTab(getInitialTab(searchParams.get("tab")));
  }, [searchParams]);

  function handleTabChange(tab) {
    setActiveTab(tab);
    if (tab === "cost") {
      router.replace("/", { scroll: false });
      return;
    }
    router.replace(`/?tab=${tab}`, { scroll: false });
  }

  return (
    <div className="app-shell min-h-screen">
      <header className="title-row">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4 md:px-8">
          <h1>The State Pension triple lock and the alternatives</h1>
        </div>
      </header>

      <main className="relative z-[1] mx-auto max-w-[1400px] px-6 py-10 md:px-8 md:py-12">
        <SampleBanner data={data} />
        <div className="animate-[fadeIn_0.4s_ease-out]">
          <p className="mb-3 text-[1.05rem] leading-relaxed text-slate-600">
            The triple lock is current policy. It raises the basic and new State Pension each year
            by the highest of CPI inflation, earnings growth or 2.5%. This dashboard uses{" "}
            <a href="https://policyengine.org/uk" target="_blank" rel="noreferrer" className="underline">
              PolicyEngine UK
            </a>{" "}
            to compare it with three alternatives: a double lock, an earnings link and a CPI link
            {period ? `, ${period}` : ""}.
          </p>
          <p className="mb-3 text-[1.05rem] leading-relaxed text-slate-600">
            <strong>Cost</strong> shows the saving from each alternative.{" "}
            <strong>Who&apos;s affected</strong> shows who loses
            {groups ? `, and the change by ${groups}` : ""}. <strong>Uncertainty</strong> shows how much the cost could vary if
            inflation and earnings differ from the forecast. <strong>Methodology</strong> sets out
            the method, limitations and sources.
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

        {activeTab === "cost" && <CostTab data={data} />}
        {activeTab === "affected" && <AffectedTab data={data} />}
        {activeTab === "uncertainty" && <UncertaintyTab data={data} />}
        {activeTab === "methodology" && <MethodologyTab data={data} />}

        <footer className="mt-12 border-t border-slate-200 pt-8 text-center text-sm text-slate-500">
          <ReplicationLine data={data} />
        </footer>
      </main>
    </div>
  );
}

export default Dashboard;
