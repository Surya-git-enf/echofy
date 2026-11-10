"use client";
import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { LANGUAGE_VIDEO } from "@/lib/media";

gsap.registerPlugin(ScrollTrigger);

export default function StudioCards() {
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.utils.toArray<HTMLElement>(".studio-card").forEach((card) => {
          // The card swings in from a tilt as it scrolls into view.
          gsap.fromTo(
            card.querySelector(".tilt"),
            { rotation: 14, y: 120 },
            { rotation: 0, y: 0, ease: "power2.out", scrollTrigger: { trigger: card, start: "top 95%", end: "top 45%", scrub: 1 } },
          );
          const pop = card.querySelector(".pop");
          if (pop) {
            gsap.fromTo(pop, { y: 24 }, { y: -24, ease: "none", scrollTrigger: { trigger: card, start: "top bottom", end: "bottom top", scrub: true } });
          }
        });
      });
    },
    { scope: root },
  );

  return (
    <section ref={root} className="studio" id="studio">
      <h2 className="section-title">Studio</h2>
      <div className="studio-grid">
        <article className="studio-card">
          <div className="tilt card card-voice">
            <div className="card-bg" />
            <img className="pop" src="/cards/card1.png" alt="A listener with glowing blue headphones" />
            <h3 className="voice-title">Voice Styles</h3>
          </div>
        </article>

        <article className="studio-card">
          <div className="tilt card card-lang">
            <div className="card-bg">
              <video src={LANGUAGE_VIDEO} autoPlay muted loop playsInline preload="metadata" />
            </div>
            <h3 className="lang-title">Language Vibes</h3>
          </div>
        </article>

        <article className="studio-card">
          <div className="tilt card card-mood">
            <div className="card-bg">
              <img src="/cards/card3.png" alt="Three listeners reacting to a dubbed video" />
            </div>
            <h3 className="mood-title">Dub Moods</h3>
          </div>
        </article>
      </div>
    </section>
  );
}
