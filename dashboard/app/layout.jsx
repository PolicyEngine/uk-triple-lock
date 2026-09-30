import PolicyEngineFooter from "../src/components/PolicyEngineFooter";
import PolicyEngineHeader from "../src/components/PolicyEngineHeader";

import "./globals.css";

export const metadata = {
  title: "The Burnham plan and the triple lock | PolicyEngine",
  description:
    "The Burnham plan against the State Pension triple lock to 2039-40: how the triple lock works, what the plan saves on the OBR's forecast and on other paths, who pays, and the saving to expect, from full PolicyEngine UK microsimulation runs.",
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
