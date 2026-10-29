import Script from "next/script";

import PolicyEngineFooter from "../src/components/PolicyEngineFooter";
import PolicyEngineHeader from "../src/components/PolicyEngineHeader";

import "./globals.css";

export const metadata = {
  title: "Burnham plan vs the triple lock | PolicyEngine",
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
        {/* Google Analytics: policyengine.org's GA4 property; this app is served at
            policyengine.org/uk/triple-lock through a rewrite, where the main site's GA does not reach. */}
        {process.env.NODE_ENV === "production" && (
          <>
            <Script
              src="https://www.googletagmanager.com/gtag/js?id=G-2YHG89FY0N"
              strategy="afterInteractive"
            />
            <Script id="google-analytics" strategy="afterInteractive">
              {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', 'G-2YHG89FY0N');`}
            </Script>
          </>
        )}
      </body>
    </html>
  );
}
