"use client";
import { useCallback, useRef, useState } from "react";
import { welcomeSeen } from "@/lib/credits";
import PageLoader from "./PageLoader";
import Navbar from "./Navbar";
import HeroCanvas from "./HeroCanvas";
import ScratchCard from "./ScratchCard";
import UploadStudio from "./UploadStudio";
import StudioCards from "./StudioCards";
import SpiralShowcase from "./SpiralShowcase";
import Footer from "./Footer";

export default function Experience() {
  const [showScratch, setShowScratch] = useState(false);
  // Fires when the hero reaches its last frame; the card only ever appears once per browser.
  const dismissed = useRef(false);
  const onHeroEnd = useCallback(() => { if (!dismissed.current && !welcomeSeen()) setShowScratch(true); }, []);

  return (
    <>
      <main id="top" style={{ position: "relative", zIndex: 1, background: "#f4f6fa", minHeight: "100vh" }}>
        <PageLoader />
        <Navbar />
        <HeroCanvas onEnd={onHeroEnd} />
        <UploadStudio />
        <StudioCards />
        <SpiralShowcase />
        <Footer />
      </main>
      {showScratch && <ScratchCard onClose={() => { dismissed.current = true; setShowScratch(false); }} />}
    </>
  );
}
