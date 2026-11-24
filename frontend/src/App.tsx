import { type ReactNode, useEffect } from "react";
import { Header } from "./components/Header";
import { SourceProvider } from "./components/SourcePanel";
import { Stepper } from "./components/Stepper";
import { Banner, Button, Spinner } from "./components/ui";
import { useHashRoute } from "./hooks/useHashRoute";
import { useStudy } from "./hooks/useStudy";
import { unlockedSteps } from "./lib/highlight";
import { EvidenceStep } from "./pages/EvidenceStep";
import { Home } from "./pages/Home";
import { InputsStep } from "./pages/InputsStep";
import { NextStep } from "./pages/NextStep";
import { ReviewStep } from "./pages/ReviewStep";

export default function App() {
  const { route, go } = useHashRoute();
  const home = () => go({ page: "home" });

  if (route.page === "home") {
    return (
      <Shell onHome={home}>
        <Home onOpen={(id) => go({ page: "study", id, step: 1 })} />
      </Shell>
    );
  }
  return <StudyView id={route.id} step={route.step} go={(step) => go({ page: "study", id: route.id, step })} onHome={home} />;
}

function Shell({ children, onHome, costLabel }: { children: ReactNode; onHome: () => void; costLabel?: string }) {
  return (
    <div className="min-h-screen">
      <Header onHome={onHome} costLabel={costLabel} />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}

function StudyView({ id, step, go, onHome }: { id: string; step: number; go: (n: number) => void; onHome: () => void }) {
  const { study, setStudy, error, refresh } = useStudy(id);

  const approved = study?.status === "approved";
  const hasResult = !!study?.result && study.status !== "analyzing";
  const unlocked = unlockedSteps({ hasResult, approved });
  const allowed = unlocked.includes(step);

  // A deep link to a locked step (e.g. #/study/x/4 before approval) falls back
  // to the furthest step the study has reached.
  useEffect(() => {
    if (study && !allowed) go(unlocked[unlocked.length - 1] ?? 1);
  }, [study, allowed, unlocked, go]);

  if (error && !study) {
    return (
      <Shell onHome={onHome}>
        <Banner tone="rose" title={error.status === 404 ? "Study not found" : "Could not load the study"}>
          <p>{error.message}</p>
          <Button variant="secondary" className="mt-2" onClick={onHome}>
            Back to start
          </Button>
        </Banner>
      </Shell>
    );
  }
  if (!study) {
    return (
      <Shell onHome={onHome}>
        <p className="flex items-center gap-2 text-stone-600">
          <Spinner /> Loading study…
        </p>
      </Shell>
    );
  }

  const done = [
    ...(hasResult ? [1, 2] : []),
    ...(approved ? [3] : []),
  ];

  return (
    <Shell onHome={onHome} costLabel={study.cost_label}>
      <SourceProvider studyId={study.id}>
        <div className="mb-6">
          <button type="button" onClick={onHome} className="text-sm text-stone-500 hover:text-stone-800">
            ← All studies
          </button>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-stone-900">{study.name}</h1>
        </div>
        <Stepper current={step} unlocked={unlocked} done={done} onSelect={go} />
        {step === 1 || !allowed ? (
          <InputsStep study={study} setStudy={setStudy} refresh={refresh} goStep={go} />
        ) : step === 2 ? (
          <EvidenceStep study={study} goStep={go} />
        ) : step === 3 ? (
          <ReviewStep study={study} setStudy={setStudy} goStep={go} />
        ) : (
          <NextStep study={study} />
        )}
      </SourceProvider>
    </Shell>
  );
}
