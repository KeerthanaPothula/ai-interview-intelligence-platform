import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react';

export interface CarouselSlide {
  src: string;
  label: string;
}

const AUTO_ADVANCE_MS = 4500;

export function ScreenshotsCarousel({ slides }: { slides: CarouselSlide[] }) {
  const [index, setIndex] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  // Explicit user override, independent of hover/focus — the only way a
  // touch or screen-reader user (neither of which triggers hover) can stop
  // an auto-advancing carousel, per WCAG 2.2.2 (Pause, Stop, Hide).
  const [userPaused, setUserPaused] = useState(false);
  const reducedMotion = useRef(false);

  useEffect(() => {
    reducedMotion.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  const paused = hovered || focused || userPaused;

  useEffect(() => {
    if (paused || reducedMotion.current) return;
    const t = setInterval(() => {
      setIndex((i) => (i + 1) % slides.length);
    }, AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [paused, slides.length]);

  const goTo = (i: number) => setIndex(((i % slides.length) + slides.length) % slides.length);

  return (
    <div
      className="lp-carousel"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false);
      }}
      role="region"
      aria-roledescription="carousel"
      aria-label="Product screenshots"
    >
      <div className="lp-carousel-frame">
        {slides.map((slide, i) => (
          <img
            key={slide.src}
            src={slide.src}
            alt={slide.label}
            className={`lp-carousel-slide${i === index ? ' active' : ''}`}
            loading="lazy"
          />
        ))}
        <button
          type="button"
          className="lp-carousel-arrow lp-carousel-arrow--prev"
          onClick={() => goTo(index - 1)}
          aria-label="Previous screenshot"
        >
          <ChevronLeft size={20} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="lp-carousel-arrow lp-carousel-arrow--next"
          onClick={() => goTo(index + 1)}
          aria-label="Next screenshot"
        >
          <ChevronRight size={20} aria-hidden="true" />
        </button>
      </div>
      <div className="lp-carousel-footer">
        <div className="lp-carousel-caption">{slides[index].label}</div>
        <button
          type="button"
          className="lp-carousel-play-toggle"
          onClick={() => setUserPaused((p) => !p)}
          aria-label={userPaused ? 'Resume automatic slideshow' : 'Pause automatic slideshow'}
          aria-pressed={userPaused}
        >
          {userPaused ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
        </button>
      </div>
      <div className="lp-carousel-dots" role="tablist" aria-label="Select screenshot">
        {slides.map((slide, i) => (
          <button
            key={slide.src}
            type="button"
            className={`lp-carousel-dot${i === index ? ' active' : ''}`}
            onClick={() => goTo(i)}
            role="tab"
            aria-selected={i === index}
            aria-label={slide.label}
          />
        ))}
      </div>
    </div>
  );
}
