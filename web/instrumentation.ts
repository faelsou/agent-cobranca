const dsn = () => process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN || "";

export async function register(): Promise<void> {
  const value = dsn();
  if (!value) return;

  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn: value,
    environment: process.env.SENTRY_ENVIRONMENT || process.env.NODE_ENV,
    tracesSampleRate: 0.1,
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    },
  });
}

type RequestErrorContext = {
  routerKind: "Pages Router" | "App Router";
  routePath: string;
  routeType: "render" | "route" | "action" | "middleware";
  renderSource?:
    | "react-server-components"
    | "react-server-components-payload"
    | "server-rendering";
  revalidateReason: "on-demand" | "stale" | undefined;
};

export async function onRequestError(
  error: unknown,
  request: Readonly<{
    path: string;
    method: string;
    headers: NodeJS.Dict<string | string[]>;
  }>,
  context: Readonly<RequestErrorContext>,
): Promise<void> {
  if (!dsn()) return;
  const Sentry = await import("@sentry/nextjs");
  await Sentry.captureRequestError(error, request, context);
}
