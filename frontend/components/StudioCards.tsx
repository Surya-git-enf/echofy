"use client";
import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { LANGUAGE_VIDEO } from "@/lib/media";
import SoundToggle from "./SoundToggle";

gsap.registerPlugin(ScrollTrigger);

export default function StudioCards() {
  const root = useRef<HTMLElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const langVideo = useRef<HTMLVideoElement>(null);

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
        const slide = gsap.to(strip, {
          x: () => -travel(),
          ease: "none",
          scrollTrigger: {
            trigger: pin.current,
            pin: true,
            scrub: 1,
            anticipatePin: 1,
            end: () => "+=" + travel(),
            invalidateOnRefresh: true,
          },
        });

        // Each card swings in from 40 degrees, settles upright in the middle of the screen, then swings out.
        gsap.utils.toArray<HTMLElement>(".studio-card", section).forEach((card) => {
          const range = { trigger: card, containerAnimation: slide, start: "left right", end: "right left" };
          gsap
            .timeline({ scrollTrigger: { ...range, scrub: 1 } })
            .fromTo(card.querySelector(".tilt"), { rotation: 40, y: 150 }, { rotation: 0, y: 0, duration: 2, ease: "power2.out" })
            .to(card.querySelector(".tilt"), { rotation: 40, y: 150, duration: 2, ease: "power2.in" });

          const pop = card.querySelector(".pop");
          if (pop) gsap.fromTo(pop, { y: 30 }, { y: -30, ease: "none", scrollTrigger: { ...range, scrub: true } });
        });

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
                <video ref={langVideo} src={LANGUAGE_VIDEO} autoPlay muted loop playsInline preload="metadata" />
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
