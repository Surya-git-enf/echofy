"use client";
import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { LANGUAGE_VIDEO } from "@/lib/media";
import { useNearViewport } from "@/hooks/useNearViewport";
import SoundToggle from "./SoundToggle";

gsap.registerPlugin(ScrollTrigger);

export default function StudioCards() {
  const root = useRef<HTMLElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const langVideo = useRef<HTMLVideoElement>(null);

  const near = useNearViewport(root);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const section = root.current;
        const strip = track.current;
        if (!section || !strip) return;

        // Pin the section and slide the cards sideways as the page scrolls.
        section.classList.add("is-pinned");
        const travel = () => strip.scrollWidth - window.innerWidth;
        const cards = gsap.utils.toArray<HTMLElement>(".studio-card", section);

        // A card is upright when its centre is mid-screen and swings away as it moves off either side.
        // Driven by where the card actually is, so nothing moves until the pinned scroll begins.
        const swing = () => {
          const mid = window.innerWidth / 2;
          cards.forEach((card) => {
            const box = card.getBoundingClientRect();
            const d = Math.max(-1, Math.min(1, (box.left + box.width / 2 - mid) / box.width));
            const e = Math.abs(d);
            const eased = e * e * (3 - 2 * e);
            gsap.set(card.querySelector(".tilt"), { rotation: 40 * eased, y: 150 * eased });
            const pop = card.querySelector(".pop");
            if (pop) gsap.set(pop, { y: 30 * d });
          });
        };

        gsap.to(strip, {
          x: () => -travel(),
          ease: "none",
          onUpdate: swing,
          scrollTrigger: {
            trigger: pin.current,
            pin: true,
            scrub: 1.2,
            anticipatePin: 1,
            refreshPriority: 1,
            end: () => "+=" + travel(),
            invalidateOnRefresh: true,
            onRefresh: swing,
          },
        });
        swing();

        return () => section.classList.remove("is-pinned");
      });
    },
    { scope: root },
  );

  return (
    <section ref={root} className="studio" id="studio">
      <div ref={pin} className="studio-pin">
        <h2 className="section-title">Studio</h2>
        <div ref={track} className="studio-track">
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
                <video ref={langVideo} src={near ? LANGUAGE_VIDEO : undefined} autoPlay muted loop playsInline preload="metadata" />
              </div>
              <SoundToggle videoRef={langVideo} />
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
      </div>
    </section>
  );
}
