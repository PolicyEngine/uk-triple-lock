"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import StepTripleLock from "./StepTripleLock";
import { StepPaths } from "./StepPath";
import StepPensioner from "./StepPensioner";
import StepPopulation from "./StepPopulation";
import SummaryTab from "./SummaryTab";
import LandingTab from "./LandingTab";
import MethodTab from "./MethodTab";
import SampleBanner from "./SampleBanner";
import { fyLabel, getExpectedValue, getHorizon, getRunsWithTables, getScenarioHeadline, isPreBudget, isScenariosOnly } from "../lib/dataHelpers";
import { readTrajectories } from "../lib/trajectoryHelpers";
import { trajectoryLabels } from "./PathCharts";
import { ReplicationLine } from "./Benchmarks";
import { SubTabs, TabLayout } from "./ui";

export const TAB_OPTIONS = [
  { id: "budget", label: "Budget impact" },
  { id: "triple-lock", label: "How the triple lock works" },
  { id: "paths", label: "Forecast paths" },
  { id: "households", label: "Distributional impact" },
  { id: "method", label: "Methodology" },
];
export const DEFAULT_TAB = "budget";



const METHOD_SECTIONS = [
  { id: "how", title: "How we model it" },
  { id: "inputs", title: "What we use" },
  { id: "assumptions", title: "Our assumptions" },
  { id: "limitations", title: "Limitations" },
];

// Each tab's sections, for the "On this tab" links (the ids are set in the sections themselves).
const BUDGET_SECTIONS = [
  { id: "at-a-glance", title: "At a glance" },
  { id: "each-year", title: "Each year" },
  { id: "choices", title: "Comparisons and choices" },
];
// A pre-Budget (b or c) file: the model-conditional distribution, then the scenario envelope beside it.
const PRE_BUDGET_EV_SECTIONS = [
  { id: "at-a-glance", title: "Across the paths" },
  { id: "each-year", title: "Each year" },
  { id: "choices", title: "Comparisons and choices" },
];
// A scenarios-only file (no expected value) has no year-by-year spread of the saving.
const SCENARIO_BUDGET_SECTIONS = [
  { id: "at-a-glance", title: "The scenarios" },
  { id: "choices", title: "Comparisons" },
];
const PATH_SECTIONS = [
  { id: "path-picker", title: "Pick a path" },
  { id: "path-pension", title: "Headline figures" },
  { id: "path-rises", title: "Each April's rise" },
  { id: "path-level", title: "The pension's level" },
];
const PENSIONER_SECTIONS = [
  { id: "pensioner-pick", title: "Pick a pensioner" },
  { id: "pensioner-cards", title: "Headline figures" },
  { id: "pensioner-chart", title: "How the change adds up" },
];
const HOUSEHOLD_SECTIONS = [
  { id: "everyone", title: "All households" },
  { id: "groups", title: "By group" },
];
const HOUSEHOLD_VIEWS = [
  { id: "everyone", label: "The whole population" },
  { id: "pensioner", label: "Example pensioners" },
];
const TRIPLE_LOCK_SECTIONS = [
  { id: "rule", title: "The rule" },
  { id: "earlier", title: "If the plan had started earlier" },
];

// Links to the earlier six-step tabs still land on the tab that now holds them.
const OLD_TABS = { summary: "budget", cost: "budget", central: "paths", path: "paths", pensioner: "households", everyone: "households" };

function getInitialTab(tabParam) {
  const tab = OLD_TABS[tabParam] ?? tabParam;
  if (TAB_OPTIONS.some((t) => t.id === tab)) {
    return tab;
  }
  return DEFAULT_TAB;
}

export function Dashboard({ data }) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState(() => getInitialTab(searchParams.get("tab")));
  const [pathId, setPathId] = useState("central");
  // The Forecast paths tab opens on the OBR central forecast; a path picked there is also the one the Distributional
  // impact tab shows.
  const [forecastPath, setForecastPath] = useState("central");
  const [householdView, setHouseholdView] = useState("everyone");
  const { trajectories } = readTrajectories(data);
  const records = getRunsWithTables(data);
  const labels = trajectoryLabels(data);
  const horizon = getHorizon(data);
  const scenariosOnly = isScenariosOnly(data);
  const nPaths = getExpectedValue(data)?.nDraws;
  const preBudgetEv = isPreBudget(data) && Boolean(getExpectedValue(data)) && Boolean(getScenarioHeadline(data));
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
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4 md:px-10 lg:pl-24">
          <h1>The Burnham plan vs the triple lock</h1>
        </div>
      </header>

      <main className="relative z-[1] mx-auto max-w-[1600px] px-6 pt-10 pb-6 md:px-10 md:pt-12 md:pb-8 lg:pl-24 lg:pr-[284px]">
        <SampleBanner data={data} />
        <div className="animate-[fadeIn_0.4s_ease-out]">
          <p className="mb-3 text-[1.1rem] leading-relaxed text-slate-700" data-testid="intro">
            The{" "}<strong className="font-semibold text-slate-900">triple lock</strong>{" "}raises the State Pension each April by{" "}
            <strong className="font-semibold text-slate-900">the highest of CPI inflation, earnings growth and 2.5%</strong>. On 29 September 2026 Prime Minister
            Andy Burnham{" "}
            <a
              href="https://www.bbc.co.uk/news/live/c6x2zrv774gvt?post=asset%3A7a078b64-1a5e-4ab2-995f-6afcb5daae5d#post"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              said
            </a>{" "}
            he would{" "}<strong className="font-semibold text-slate-900">replace it from 2030</strong>{" "}with a rise of{" "}
            <strong className="font-semibold text-slate-900">at least prices or 2.5%</strong>{" "}that &quot;holds its value relative to earnings over
            time&quot;.{" "}<strong className="font-semibold text-slate-900">We cost that plan against the triple lock</strong>{" "}with{" "}
            <a href="https://policyengine.org/uk" target="_blank" rel="noreferrer" className="underline">
              PolicyEngine UK
            </a>
            {period ? ` from ${period}` : ""},{" "}
            {scenariosOnly
              ? "on the OBR central forecast and scenarios around it"
              : <>on{" "}<strong className="font-semibold text-slate-900">{nPaths ? nPaths.toLocaleString("en-GB") : "thousands of"} simulated paths</strong>{" "}of prices and earnings centred on the OBR&apos;s forecast</>}
            , as the saving depends on how often the two swap the lead.
          </p>
          <p className="mb-3 text-[0.95rem] text-slate-600" data-testid="paper-link">
            <a href={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/paper/`} className="font-medium underline">
              Read the working paper
            </a>
            : the full method, results and limitations.
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

        {activeTab === "budget" && (
          <TabLayout sections={scenariosOnly ? SCENARIO_BUDGET_SECTIONS : preBudgetEv ? PRE_BUDGET_EV_SECTIONS : BUDGET_SECTIONS}>
            <LandingTab data={data} />
            <SummaryTab data={data} />
          </TabLayout>
        )}
        {activeTab === "paths" && (
          <TabLayout sections={PATH_SECTIONS}>
            <StepPaths
              data={data}
              trajectories={trajectories}
              labels={labels}
              pathId={forecastPath}
              onPath={(id) => {
                setForecastPath(id);
                setPathId(id);
              }}
            />
          </TabLayout>
        )}
        {activeTab === "households" && (
          <TabLayout sections={householdView === "everyone" ? HOUSEHOLD_SECTIONS : PENSIONER_SECTIONS}>
            <SubTabs options={HOUSEHOLD_VIEWS} value={householdView} onChange={setHouseholdView} />
            {householdView === "everyone" ? (
              <StepPopulation data={data} records={records} trajectories={trajectories} labels={labels} pathId={pathId} onPath={setPathId} />
            ) : (
              <StepPensioner data={data} records={records} labels={labels} pathId={pathId} onPath={setPathId} />
            )}
          </TabLayout>
        )}
        {activeTab === "triple-lock" && (
          <TabLayout sections={TRIPLE_LOCK_SECTIONS}>
            <StepTripleLock data={data} />
          </TabLayout>
        )}
        {activeTab === "method" && (
          <TabLayout sections={METHOD_SECTIONS}>
            <MethodTab data={data} />
          </TabLayout>
        )}

        <footer className="mt-10 border-t border-slate-200 pt-5 text-center text-sm text-slate-500">
          <ReplicationLine data={data} />
        </footer>
      </main>
    </div>
  );
}

export default Dashboard;
