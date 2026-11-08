import { useEscapeSchliessen } from "../utils/useEscapeSchliessen";
import { EulenwerkAbout } from "./EulenwerkAbout";
import pkg from "../../package.json";

/** Über-Dialog im einheitlichen Eulenwerk-Layout (siehe D:\Dropbox\Design\CI\Design-System). */
export function AboutDialog({ onClose }: { onClose: () => void }) {
  useEscapeSchliessen(onClose);
  return (
    <EulenwerkAbout
      open
      onClose={onClose}
      app="Geschichten Erzähler"
      version={pkg.version}
      logo="/favicon.svg?v=2"
      description="Eine geführte Fünf-Rollen-Pipeline für KI-geschriebene Geschichten mit lokalen Ollama-Modellen – Architekt, Autor, Prüfer, Lektor und Übersetzer."
      stack={["React 19", "TypeScript", "Vite", "Tailwind 4", "FastAPI", "Ollama", "stable-diffusion.cpp"]}
      github="https://github.com/thunder312/GeschichtenErzaehler"
    />
  );
}
