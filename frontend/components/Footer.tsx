import { DISCORD_HANDLE, INSTAGRAM_URL } from "@/lib/media";

export default function Footer() {
  return (
    <footer className="footer" id="support">
      <div>
        <h2 className="footer-title">Support</h2>
        <p>Something not working, or want a language added? Message us and we will get back to you.</p>
      </div>
      <ul className="socials">
        <li>
          <a href={INSTAGRAM_URL} target="_blank" rel="noopener noreferrer" aria-label="Echofy on Instagram">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="5" />
              <circle cx="12" cy="12" r="4.2" />
              <circle cx="17.3" cy="6.7" r="1" fill="currentColor" stroke="none" />
            </svg>
            <span>Instagram</span>
          </a>
        </li>
        <li>
          <span className="social-static" title="Discord username">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true">
              <path d="M5.5 7.5c1.7-1.2 3.2-1.6 3.2-1.6l.3.6c1-.2 2-.2 3 0l.3-.6s1.5.4 3.2 1.6c1.5 2.4 2.1 5 1.9 8.1-1.3 1-2.7 1.5-2.7 1.5l-.8-1.3c.5-.2.9-.4 1.3-.7l-.3-.2c-2.5 1.1-5.200 1.1-7.700 0l-.3.2c.4.3.8.5 1.300.7l-.8 1.3s-1.4-.5-2.700-1.500C4.2 12.600 4.900 9.900 5.500 7.500z" />
              <circle cx="9.300" cy="12" r="1.200" fill="#EEF1F5" />
              <circle cx="14.700" cy="12" r="1.200" fill="#EEF1F5" />
            </svg>
            <span>Discord: {DISCORD_HANDLE}</span>
          </span>
        </li>
      </ul>
      <p className="legal">Echofy. Dub your video into any language.</p>
      <p className="wordmark" aria-hidden="true">Echofy</p>
    </footer>
  );
}
