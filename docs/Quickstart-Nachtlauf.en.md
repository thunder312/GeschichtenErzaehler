🇩🇪 [Deutsche Version](Quickstart-Nachtlauf.md)

# Quickstart: server → PC → write overnight → back

Full version with test scenario and pitfalls:
[Anwendungsfall-Nachtlauf-lokal.en.md](Anwendungsfall-Nachtlauf-lokal.en.md).

## One-time setup

- [ ] Start the local app: `start-dev.ps1` → `http://localhost:5173`
- [ ] **Settings → 🔄 Abgleich mit Server** (Sync with server): address
      `https://geschichten.daniel-ertl.de`, user name, password →
      **Save** → **Test connection**
- [ ] **Settings → AI targets:** `PC (lokal)` (`direct`,
      `http://127.0.0.1:11434`) exists and "Test connection" succeeds

## Every time

**On the server**
1. Create the project (tab **Projects**), pick the era.
2. **Architect / Outline:** run the interview, save the outline.

**On the PC**
3. Tab **Projects → 🔄 Sync with server** → the project (status "only on the
   server") → **⬇ To the PC** → status "✓ identical".
4. In the header, click the AI target **`PC (lokal)`**; the dot must be green.
5. Stop image-AI containers, disable Windows sleep/hibernate.
6. Tab **Write → Automatic mode:** set max. passes, tick
   **⏻ Shut down PC afterwards**, start. Watch briefly until the author
   text appears live.
7. Go to bed. Leave the backend window and Docker/Ollama running.

**Next morning**
8. Switch the PC on, run `start-dev.ps1`. Tab **Write**: all chapters done?
   If not, look at the findings → **Resume**.
9. Tab **Projects → Sync** → status "⬆ PC is newer" → **⬆ To the server**.
10. On the **server:** **Check & Apply**, **Spelling**,
    **Finish check** (tick "clean up copy on the PC"),
    **State & Export**.
11. On the PC: **🧹 Remove locally**.

## Golden rules

- While the project is on the PC, do **not** work on it on the server.
- "⚠ both changed" → do not overwrite blindly (no merge, only a backup).
- Shutdown only happens after a **successful** finish, not after an
  intermediate stop or an error.
- Everything starts from the **PC**; the server cannot push anything to it.

> UI labels in quotes are translated for readability; the app itself shows
> the German texts.
