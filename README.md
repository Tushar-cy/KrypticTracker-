# KrypticTrack · Personal Neural Shadow

> A privacy-first "second brain" that logs every meaningful interaction on your Linux box, trains a compact IRL reward model with 3-4 dense layers, and layers a local TinyLLM (≈1.1B) to narrate what the neural core thinks you will do next.

---

## 🧠 Why this exists
- I want software that **thinks like me**, not like a cloud vendor.
- Every click, key press, window switch, repo pull, and terminal command carries signal about my reward function.
- By pairing **Inverse Reinforcement Learning** (behavior → reward) with relentless logging, KrypticTrack becomes a living memory of how I work and what I'm likely to do next.

---

## 🏗️ System Overview
| Layer | Purpose | Stack |
| --- | --- | --- |
| Data capture | Chrome, VS Code, Linux system daemon, Linux Brain Logger | Manifest V3, VS Code API, psutil/Xlib |
| Transport | Unified `/api/log-action` with filtering for noisy DOM/mouse spam | Flask + SQLite (encrypted) |
| Storage | `actions`, `sessions`, `predictions`, `training_runs`, `data_aggregates` | SQLite + SQLCipher |
| Neural core | 3-4 layer reward network (256→128→64→1) trained via IRL | PyTorch + custom training loop |
| LLM overlay | Tiny local LLM (≈1.1B) to summarize predictions/insights | `backend/services/llm_service.py` |
| UX | Vite + React dashboard + inline charts + modern chat without bubbles | React 18, Tailwind, Chart.js |

---

## 🧬 Neural Architecture (Why 3-4 layers?)
1. **Layer 1 (256 units, GELU)** – absorbs the fused state vector (Chrome/VSCode/System features). High width captures modality-specific nuances.
2. **Layer 2 (128 units, GELU + dropout 0.1)** – forces compression; we only keep features that consistently explain reward spikes.
3. **Layer 3 (64 units, Swish)** – low-width bottleneck improves interpretability and keeps params ≈1-2M for RTX 3050.
4. **Reward head (1 unit, linear)** – outputs scalar reward used by MaxEnt IRL + next-action predictor.

Why this shape? Because:
- Too shallow → can’t model context switches.
- Too deep → overkill for single-user data + slower retrains.
- This stack trains in <5 minutes per epoch on 3050, yet adapts quickly when daily behavior shifts.

---

## 🔁 Data Hygiene & Retention
- **Full fidelity** for the last 30 days (everything stays).
- **1% reservoir sampling** for anything older (keeps representative history without bloat).
- **Aggregated metrics** (hourly/daily/source histograms) stored forever in `data_aggregates`.
- **Never deleted**: insights, predictions, training runs.
- `/api/cleanup` endpoint runs the entire workflow so the neural model always has clean-but-complete data to learn from.

---

## 🖥️ Linux logging essentials
Run `python data_collection/linux_brain_logger.py` to capture:
- File opens/edits/saves (projects you touch)
- Terminal commands + git intent
- Network sessions + remote work
- CPU/Mem/Disk spikes (intensity of focus)
- Focus sessions (single-app >5 min)
- App launches + window changes (attention graph)

These signals feed both the neural net and the inline LLM commentary so the chat view feels alive (charts mid-stream, no "bubble" UI).

---

## 🚀 Usage
### 1. Backend
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```
_Backend auto-inits the DB, registers all blueprints, and exposes `/api/*` + `/api/cleanup`._

### 2. Frontend (Vite React)
```bash
cd frontend
npm install
npm run dev        # hot reload on :3000
npm run build      # outputs to dashboard/web/static/dist
```
Run `npm run build` before launching Flask in production—the backend now serves everything from `dashboard/web/static/dist`.

### 3. Linux Brain Logger
```bash
python data_collection/linux_brain_logger.py
```
Keep it running to log files, terminals, focus sessions, and resource spikes.

### 4. Periodic cleanup
```bash
curl -X POST http://localhost:5000/api/cleanup \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "keep_days": 30}'
```
This aggregates metrics, preserves representative samples, and deletes only the noise the neural net no longer needs.

---

## 🔮 Future Scope
- **Activity embeddings**: contrastive encoders for Chrome tab text + VS Code AST summaries.
- **Temporal reward modulation**: recurrent head that weights circadian rhythm + fatigue markers.
- **Action synthesis**: feed predicted rewards into an automation layer (launch app, open repo, prep context).
- **Federated dual-mode**: selectively sync anonymized aggregates across devices without leaking raw logs.
- **Hardware loop**: use focus signals to control ambient lighting / notifications.

---

## 🤝 Open for Contributions
Yes, this repo is personal, but great ideas are welcome.
1. **Fork + feature branch** – please keep commits scoped.
2. **Tests** – add unit/integration tests under `/tests` when you touch backend logic.
3. **Frontend** – follow the Tailwind palette (no purple gradients) and avoid chat bubbles.
4. **Describe behavior** – every PR should explain how it protects privacy and why it helps the neural brain think more like me.

If you want to propose major architectural shifts (new data sources, different IRL formulations, etc.) open an issue first so we can align on the mental model.

---

## 📜 License
Private, but permissive for collaborators. Reach out before redistributing.
