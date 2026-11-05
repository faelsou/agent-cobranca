import { Suspense } from "react";
import { TitulosScreen } from "./screen";

export default function TitulosPage() {
  return (
    <Suspense fallback={<p className="text-sm text-ink-700/70">Carregando títulos…</p>}>
      <TitulosScreen />
    </Suspense>
  );
}
