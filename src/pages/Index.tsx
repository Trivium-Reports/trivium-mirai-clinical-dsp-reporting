import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import triviumLogo from "@/assets/trivium-logo.png";
import LandingHero from "@/components/LandingHero";
import DSPReport from "@/components/DSPReport";
import { parseDSPReport, type DSPSummary } from "@/lib/dsp-data";

type AppView = "landing" | "report";

const Index = () => {
  const [view, setView] = useState<AppView>("landing");
  const [dspData, setDspData] = useState<DSPSummary | null>(null);

  useEffect(() => {
    fetch("/data/dsp.csv")
      .then(r => r.text())
      .then(text => setDspData(parseDSPReport(text)))
      .catch(err => console.error("Failed to load DSP data:", err));
  }, []);

  const dateRange = dspData
    ? (() => {
        const fmt = (d: string) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        return `${fmt(dspData.dateRange.start)} — ${fmt(dspData.dateRange.end)}`;
      })()
    : undefined;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <nav className="sticky top-0 z-50 backdrop-blur-md bg-background/80 border-b border-border print:hidden">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-18 py-4">
          <div className="flex items-center gap-0.5 cursor-pointer" onClick={() => setView("landing")}>
            <img src={triviumLogo} alt="Trivium" className="h-10 w-auto" />
            <span className="font-display font-extrabold text-xl uppercase tracking-tight">
              TRIVIUM
            </span>
          </div>
          {view === "landing" && (
            <button
              onClick={() => setView("report")}
              className="px-6 py-2.5 rounded-full bg-primary text-primary-foreground font-display font-bold text-sm uppercase tracking-wide hover:scale-105 transition-transform"
            >
              View Report
            </button>
          )}
          {view === "report" && (
            <span className="font-display font-bold text-xs uppercase tracking-widest text-muted-foreground">
              DSP Performance Report
            </span>
          )}
        </div>
      </nav>

      <main className="flex-1">
        <AnimatePresence mode="wait">
          {view === "landing" && (
            <motion.div key="landing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
              <LandingHero
                onViewReport={() => setView("report")}
                brandName={dspData?.brand}
                dateRange={dateRange}
              />
            </motion.div>
          )}
          {view === "report" && dspData && (
            <motion.div key="report" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
              <DSPReport data={dspData} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default Index;
