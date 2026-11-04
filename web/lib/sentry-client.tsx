"use client";

import { useEffect } from "react";

/** Sentry no browser só se `NEXT_PUBLIC_SENTRY_DSN` entrou no build. */
export function SentryClient() {
  useEffect(() => {
    const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
    if (!dsn) return;
    void import("@sentry/nextjs").then((Sentry) => {
      if (Sentry.getClient()) return;
      Sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "prod",
        tracesSampleRate: 0.1,
        dataCollection: {
          userInfo: false,
          cookies: false,
          httpHeaders: false,
          httpBodies: [],
          urlQueryParams: false,
        },
      });
    });
  }, []);
  return null;
}
