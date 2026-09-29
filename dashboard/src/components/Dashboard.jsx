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
  { id: "cost", label: "Budget impact" },
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
          <h1>The State Pension triple lock</h1>
        </div>
      </header>

      <main className="relative z-[1] mx-auto max-w-[1400px] px-6 py-10 md:px-8 md:py-12">
        <SampleBanner data={data} />
        <div className="animate-[fadeIn_0.4s_ease-out]">
          <p className="mb-3 text-[1.05rem] leading-relaxed text-slate-600">
            The triple lock raises the basic and new State Pension each April by the highest of CPI
            inflation, earnings growth or 2.5%. In his speech to Labour&apos;s conference on 29
            September 2026, Prime Minister Andy Burnham{" "}
            <a
              href="https://www.bbc.co.uk/news/live/c6x2zrv774gvt"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              said
            </a>{" "}
            the triple lock will stay for this Parliament and that, from April 2030, the State
            Pension will &quot;continue to rise every year at least by prices or 2.5%&quot; and
            &quot;hold its value relative to earnings over time&quot;, with the savings going to a
            National Care Service. The speech gave no formula, so we model it as a rise of at least
            the higher of CPI and 2.5% that never leaves the pension below an earnings link from
            2029-30. This dashboard uses{" "}
            <a href="https://policyengine.org/uk" target="_blank" rel="noreferrer" className="underline">
              PolicyEngine UK
            </a>{" "}
            to compare the triple lock with that plan and three other rules, each starting in April
            2030{period ? `, over ${period}` : ""}. <strong>Budget impact</strong> gives the saving to the
            government from each alternative, before and after knock-on effects on other benefits
            and tax; <strong>Who&apos;s affected</strong> gives the change in household income
            {groups ? ` by ${groups}` : ""}; <strong>Uncertainty</strong> shows how much the cost
            could vary if inflation and earnings differ from the forecast; and{" "}
            <strong>Methodology</strong> sets out the method, limitations and sources.
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
