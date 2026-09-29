import PolicyEngineFooter from "../src/components/PolicyEngineFooter";
import PolicyEngineHeader from "../src/components/PolicyEngineHeader";

import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata = {
  title: "The State Pension triple lock and the alternatives | PolicyEngine",
  description:
    "Cost, distributional impact and forecast uncertainty of the State Pension triple lock compared with a double lock, an earnings link and a CPI link, using PolicyEngine UK microsimulation.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <PolicyEngineHeader />
        {children}
        <PolicyEngineFooter />
      </body>
    </html>
  );
}
