import PolicyEngineFooter from "../src/components/PolicyEngineFooter";
import PolicyEngineHeader from "../src/components/PolicyEngineHeader";

import "./globals.css";

export const metadata = {
  title: "The adjusted Triple Lock vs the triple lock | PolicyEngine",
  description:
    "The government's adjusted Triple Lock (Budget 2026) against the State Pension triple lock to 2039-40: how the triple lock works, what the adjustment saves on the OBR's forecast and on other paths, and who pays, from full PolicyEngine UK microsimulation runs.",
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
