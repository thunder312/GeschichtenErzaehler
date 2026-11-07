/* Eulenwerk · Logo + Über-Dialog (React 18/19, TypeScript). Benötigt eulenwerk.css.
 *
 *   const [about, setAbout] = useState(false)
 *   <EulenwerkAbout open={about} onClose={() => setAbout(false)} app="GeschichtenErzähler"
 *     version="2.3.0" description="…" stack={["React", "Vite", "FastAPI"]} github="https://github.com/…" />
 */
import { useEffect, useRef, type ReactNode } from "react";

export function EulenwerkLogo({ className = "ew-logo" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth={4}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 5 C11 12 16 13 24 13 C28 13 30 15 32 16 C34 15 36 13 40 13 C48 13 53 12 56 5" />
      <circle cx="22" cy="28" r="9" /><circle cx="42" cy="28" r="9" />
      <circle fill="currentColor" stroke="none" cx="22" cy="28" r="3.2" />
      <circle fill="currentColor" stroke="none" cx="42" cy="28" r="3.2" />
      <path d="M29.5 39 L32 42.5 L34.5 39" />
      <path d="M13 28 V48 C13 54 18 59 24 59 H40 C46 59 51 54 51 48 V28" />
      <path d="M19 40 C18.5 48 19.5 54 23 59" /><path d="M45 40 C45.5 48 44.5 54 41 59" />
    </svg>
  );
}

const IconGithub = () => (
  <svg className="ew-icon" viewBox="0 0 16 16" fill="currentColor" stroke="none" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
  </svg>
);
const IconBeer = () => (
  <svg className="ew-icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M17 11h1a3 3 0 0 1 0 6h-1" /><path d="M9 12v6" /><path d="M13 12v6" />
    <path d="M14 7.5c-1 0-1.44.5-3 .5s-2-.5-3-.5-1.72.5-2.5.5a2.5 2.5 0 0 1 0-5c.78 0 1.57.5 2.5.5S9.44 2 11 2s2 1.5 3 1.5 1.72-.5 2.5-.5a2.5 2.5 0 0 1 0 5c-.78 0-1.5-.5-2.5-.5Z" />
    <path d="M5 8v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8" />
  </svg>
);
const IconSpark = () => (
  <svg className="ew-icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
  </svg>
);

export interface EulenwerkAboutProps {
  open: boolean;
  onClose: () => void;
  app: string;
  version?: string;
  description?: string;
  stack?: string[];
  github?: string;
  /** Eigenes App-Logo: URL oder React-Element. Ohne Angabe erscheint die Eulenwerk-Eule. */
  logo?: string | ReactNode;
  children?: ReactNode;
}

export function EulenwerkAbout({ open, onClose, app, version, description, stack = [], github, logo, children }: EulenwerkAboutProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const year = new Date().getFullYear();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog ref={ref} className="ew-dialog ew-about" aria-labelledby="ew-about-title"
            onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <button type="button" className="ew-btn ew-btn--ghost ew-btn--icon ew-about__close" aria-label="Schließen" onClick={onClose}>
        <svg className="ew-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
      </button>

      <div className="ew-about__head">
        {typeof logo === "string" ? <img className="ew-about__applogo" src={logo} alt="" /> : logo ? <div className="ew-about__applogo">{logo}</div> : <EulenwerkLogo />}
        <div>
          <h2 id="ew-about-title">{app}</h2>
          <p className="ew-muted">{version ? `Version ${version} · ` : ""}Ein Eulenwerk-Projekt</p>
        </div>
      </div>

      <div className="ew-about__body">
        {description && <p className="ew-about__desc">{description}</p>}
        <h4>Entwickelt von</h4>
        <div className="ew-about__people">
          <div className="ew-about__person">
            <div className="ew-avatar">DE</div>
            <div>
              <strong>Daniel Ertl</strong>
              <div className="ew-muted">Idee &amp; Entwicklung</div>
              <div className="ew-about__links">
                <a href="https://github.com/thunder312" target="_blank" rel="noopener"><IconGithub />github.com/thunder312</a>
                <a href="https://buymeacoffee.com/dertl" target="_blank" rel="noopener"><IconBeer />Buy me a beer</a>
                {github && <a href={github} target="_blank" rel="noopener"><IconGithub />Quellcode</a>}
              </div>
            </div>
          </div>
          <div className="ew-about__person">
            <div className="ew-avatar ew-avatar--ai">AI</div>
            <div>
              <strong>Claude</strong>
              <div className="ew-muted">KI-Assistent beim Programmieren</div>
              <div className="ew-about__links">
                <a href="https://claude.ai" target="_blank" rel="noopener"><IconSpark />claude.ai</a>
              </div>
            </div>
          </div>
        </div>
        {stack.length > 0 && (
          <>
            <h4>Technik</h4>
            <div className="ew-about__stack">{stack.map((s) => <span key={s} className="ew-badge">{s}</span>)}</div>
          </>
        )}
        {children}
      </div>

      <div className="ew-about__foot">
        <a className="ew-brand" href="https://daniel-ertl.de" target="_blank" rel="noopener"><EulenwerkLogo />Eulenwerk – Software aus der Freizeit</a>
        <span>© {year} Daniel Ertl</span>
      </div>
    </dialog>
  );
}

export default EulenwerkAbout;
