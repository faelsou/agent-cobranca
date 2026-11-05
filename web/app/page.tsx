export default function Home() {
  return (
    <main className="grid min-h-screen place-items-center bg-paper-50">
      <p className="text-sm text-ink-700/70">Abrindo o painel…</p>
      <script
        dangerouslySetInnerHTML={{
          __html: `location.replace(localStorage.getItem("cobranca.token") ? "/inicio" : "/login")`,
        }}
      />
    </main>
  );
}
